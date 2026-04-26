from __future__ import annotations

import logging
import threading
import time
import duckdb
import pandas as pd
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_lock_conflict(exc: duckdb.IOException) -> bool:
    text = str(exc)
    return "Could not set lock on file" in text or "Conflicting lock is held" in text


def _open_connection(*, read_only: bool, retries: int, delay: float) -> duckdb.DuckDBPyConnection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = settings.data_dir / "duckdb_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            con = duckdb.connect(str(settings.duckdb_path), read_only=read_only)
            try:
                con.execute("PRAGMA memory_limit='4GB'")
                con.execute("PRAGMA threads=4")
                con.execute(f"PRAGMA temp_directory='{temp_dir}'")
            except Exception:  # pragma: no cover - defensive: never fail on PRAGMA
                logger.warning("Failed to apply DuckDB memory PRAGMAs", exc_info=True)
            return con
        except duckdb.IOException as exc:
            if _is_lock_conflict(exc) and attempt < retries - 1:
                wait_seconds = min(delay * (2 ** attempt), 10.0)
                time.sleep(wait_seconds)
                continue
            raise


def _is_recoverable_read_error(exc: Exception) -> bool:
    recoverable_types = (
        duckdb.ConnectionException,
        duckdb.FatalException,
        duckdb.IOException,
        duckdb.InternalException,
        duckdb.OperationalError,
    )
    return isinstance(exc, recoverable_types)


class _ReadOnlyConnectionProxy:
    def __init__(self, manager: "_SharedReadConnectionManager", retries: int, delay: float) -> None:
        self._manager = manager
        self._retries = retries
        self._delay = delay

    def __enter__(self) -> "_ReadOnlyConnectionProxy":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._manager.release_thread_cursor()
        return False

    def execute(self, query: str, parameters: object | None = None):
        cursor, generation = self._manager.get_cursor(retries=self._retries, delay=self._delay)
        try:
            if parameters is None:
                return cursor.execute(query)
            return cursor.execute(query, parameters)
        except Exception as exc:
            if not _is_recoverable_read_error(exc):
                raise
            logger.warning("DuckDB read cursor failed; recreating shared read connection: %s", exc)
            self._manager.reconnect(
                retries=self._retries,
                delay=self._delay,
                expected_generation=generation,
            )
            cursor, _ = self._manager.get_cursor(retries=self._retries, delay=self._delay)
            if parameters is None:
                return cursor.execute(query)
            return cursor.execute(query, parameters)

    def __getattr__(self, name: str):
        cursor, _ = self._manager.get_cursor(retries=self._retries, delay=self._delay)
        return getattr(cursor, name)


class _SharedReadConnectionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread_local = threading.local()
        self._base_connection: duckdb.DuckDBPyConnection | None = None
        self._generation = 0

    def get_proxy(self, *, retries: int, delay: float) -> _ReadOnlyConnectionProxy:
        return _ReadOnlyConnectionProxy(self, retries, delay)

    def get_cursor(self, *, retries: int, delay: float) -> tuple[duckdb.DuckDBPyConnection, int]:
        with self._lock:
            base_connection = self._ensure_base_connection_locked(retries=retries, delay=delay)
            state_generation = getattr(self._thread_local, "generation", -1)
            cursor = getattr(self._thread_local, "cursor", None)
            if cursor is None or state_generation != self._generation:
                cursor = base_connection.cursor()
                self._thread_local.cursor = cursor
                self._thread_local.generation = self._generation
            return cursor, self._generation

    def reconnect(self, *, retries: int, delay: float, expected_generation: int | None = None) -> None:
        with self._lock:
            if expected_generation is not None and expected_generation != self._generation:
                return
            self._close_base_connection_locked()
            self._ensure_base_connection_locked(retries=retries, delay=delay)

    def close(self) -> None:
        with self._lock:
            self._close_base_connection_locked()
        self._thread_local.cursor = None
        self._thread_local.generation = -1

    def release_thread_cursor(self) -> None:
        cursor = getattr(self._thread_local, "cursor", None)
        self._thread_local.cursor = None
        self._thread_local.generation = -1
        if cursor is None:
            return
        try:
            cursor.close()
        except Exception:  # pragma: no cover - defensive cleanup
            logger.debug("Failed to close DuckDB read cursor cleanly", exc_info=True)

    def _ensure_base_connection_locked(self, *, retries: int, delay: float) -> duckdb.DuckDBPyConnection:
        if self._base_connection is None:
            self._base_connection = _open_connection(read_only=True, retries=retries, delay=delay)
            self._generation += 1
        return self._base_connection

    def _close_base_connection_locked(self) -> None:
        connection = self._base_connection
        self._base_connection = None
        self._generation += 1
        if connection is None:
            return
        try:
            connection.close()
        except Exception:  # pragma: no cover - defensive cleanup
            logger.debug("Failed to close shared DuckDB read connection cleanly", exc_info=True)


_READ_CONNECTION_MANAGER = _SharedReadConnectionManager()


def get_connection(*, read_only: bool = False, retries: int = 20, delay: float = 0.5) -> duckdb.DuckDBPyConnection:
    """Open DuckDB connection with retry to mitigate writer lock contention."""
    if read_only:
        return _READ_CONNECTION_MANAGER.get_proxy(retries=retries, delay=delay)
    return _open_connection(read_only=False, retries=retries, delay=delay)


def close_read_connection() -> None:
    _READ_CONNECTION_MANAGER.close()


def upsert_daily(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    if "ts_code" not in df.columns or "trade_date" not in df.columns:
        raise ValueError("daily data must include ts_code and trade_date")

    daily_base = settings.data_dir / "raw" / "daily"
    daily_base.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    data["trade_date"] = data["trade_date"].astype(str)
    data["year"] = data["trade_date"].str[:4]

    # Use pandas to_parquet directly for better performance
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = daily_base / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        new_rows = group.drop(columns=["year"])
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
    return df.shape[0]


def upsert_adj_factor(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    if "ts_code" not in df.columns or "trade_date" not in df.columns:
        raise ValueError("adj_factor data must include ts_code and trade_date")

    base_dir = settings.data_dir / "raw" / "adj_factor"
    base_dir.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    data["trade_date"] = data["trade_date"].astype(str)
    data["year"] = data["trade_date"].str[:4]

    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = base_dir / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        new_rows = group.drop(columns=["year"])
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
    return df.shape[0]


def upsert_daily_basic(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    if "ts_code" not in df.columns or "trade_date" not in df.columns:
        raise ValueError("daily_basic data must include ts_code and trade_date")

    base_dir = settings.data_dir / "raw" / "daily_basic"
    base_dir.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    data["trade_date"] = data["trade_date"].astype(str)
    data["year"] = data["trade_date"].str[:4]

    # Use pandas to_parquet directly for better performance
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = base_dir / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows = group.drop(columns=["year"])
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
    return df.shape[0]


def upsert_daily_limit(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    if "ts_code" not in df.columns or "trade_date" not in df.columns:
        raise ValueError("daily_limit data must include ts_code and trade_date")

    base_dir = settings.data_dir / "raw" / "daily_limit"
    base_dir.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    data["trade_date"] = data["trade_date"].astype(str)
    data["year"] = data["trade_date"].str[:4]

    # Use pandas to_parquet directly for better performance
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = base_dir / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows = group.drop(columns=["year"])
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
    return df.shape[0]


def has_stock_data(ts_code: str) -> bool:
    """Check if stock has any data in parquet files (daily, daily_basic, or daily_limit)."""
    daily_root = settings.data_dir / "raw" / "daily" / f"ts_code={ts_code}"
    if not daily_root.exists():
        return False

    part_glob = str(daily_root / "year=*/part-*.parquet")
    query = "SELECT COUNT(*) as cnt FROM read_parquet(?) WHERE ts_code = ?"
    with get_connection(read_only=True) as con:
        try:
            result = con.execute(query, [part_glob, ts_code]).fetchone()
            return result[0] > 0 if result else False
        except duckdb.CatalogException:
            return False


def list_daily(ts_code: str, limit: int | None = None) -> list[dict[str, object]]:
    daily_root = settings.data_dir / "raw" / "daily" / f"ts_code={ts_code}"
    if not daily_root.exists():
        return []

    part_glob = str(daily_root / "year=*/part-*.parquet")
    if limit is not None and limit > 0:
        query = (
            "SELECT ts_code, trade_date, open, high, low, close, vol, amount "
            "FROM ("
            "  SELECT ts_code, trade_date, open, high, low, close, vol, amount "
            "  FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date DESC LIMIT ?"
            ") ORDER BY trade_date"
        )
        params = [part_glob, ts_code, limit]
    else:
        query = (
            "SELECT ts_code, trade_date, open, high, low, close, vol, amount "
            "FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date"
        )
        params = [part_glob, ts_code]
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, params).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_daily_basic(ts_code: str) -> list[dict[str, object]]:
    daily_basic_root = settings.data_dir / "raw" / "daily_basic" / f"ts_code={ts_code}"
    if not daily_basic_root.exists():
        return []

    part_glob = str(daily_basic_root / "year=*/part-*.parquet")
    query = (
        "SELECT ts_code, trade_date, close, turnover_rate, turnover_rate_f, "
        "volume_ratio, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm, "
        "total_share, float_share, free_share, total_mv, circ_mv "
        "FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date"
    )
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, [part_glob, ts_code]).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_stk_limit(ts_code: str) -> list[dict[str, object]]:
    daily_limit_root = settings.data_dir / "raw" / "daily_limit" / f"ts_code={ts_code}"
    if not daily_limit_root.exists():
        return []

    part_glob = str(daily_limit_root / "year=*/part-*.parquet")
    query = (
        "SELECT trade_date, ts_code, pre_close, up_limit, down_limit "
        "FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date"
    )
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, [part_glob, ts_code]).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_adj_factor(ts_code: str, limit: int | None = None) -> list[dict[str, object]]:
    adj_factor_root = settings.data_dir / "raw" / "adj_factor" / f"ts_code={ts_code}"
    if not adj_factor_root.exists():
        return []

    part_glob = str(adj_factor_root / "year=*/part-*.parquet")
    if limit is not None and limit > 0:
        query = (
            "SELECT ts_code, trade_date, adj_factor "
            "FROM ("
            "  SELECT ts_code, trade_date, adj_factor "
            "  FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date DESC LIMIT ?"
            ") ORDER BY trade_date"
        )
        params = [part_glob, ts_code, limit]
    else:
        query = (
            "SELECT ts_code, trade_date, adj_factor "
            "FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date"
        )
        params = [part_glob, ts_code]
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, params).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_indicators(ts_code: str, limit: int | None = None) -> list[dict[str, object]]:
    """Get technical indicators for a stock."""
    indicators_root = settings.data_dir / "features" / "indicators" / f"ts_code={ts_code}"
    if not indicators_root.exists():
        return []

    part_glob = str(indicators_root / "year=*/part-*.parquet")
    if limit is not None and limit > 0:
        query = (
            "SELECT * FROM ("
            "  SELECT * FROM read_parquet(?, union_by_name = true) "
            "  WHERE ts_code = ? ORDER BY trade_date DESC LIMIT ?"
            ") ORDER BY trade_date"
        )
        params = [part_glob, ts_code, limit]
    else:
        query = (
            "SELECT * FROM read_parquet(?, union_by_name = true) "
            "WHERE ts_code = ? ORDER BY trade_date"
        )
        params = [part_glob, ts_code]
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, params).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_latest_daily_changes(ts_codes: list[str]) -> dict[str, dict[str, object]]:
    if not ts_codes:
        return {}

    daily_root = settings.data_dir / "raw" / "daily"
    if not daily_root.exists():
        return {}

    part_globs: list[str] = []
    for code in ts_codes:
        code_dir = daily_root / f"ts_code={code}"
        if code_dir.exists():
            part_globs.append(str(code_dir / "year=*/part-*.parquet"))
    if not part_globs:
        return {}

    query = f"""
        SELECT ts_code,
               trade_date,
               COALESCE(change, close - pre_close) AS change,
               COALESCE(pct_chg, (close - pre_close) / NULLIF(pre_close, 0) * 100) AS pct_chg
        FROM (
            SELECT ts_code,
                   trade_date,
                   change,
                   pct_chg,
                   close,
                   pre_close,
                   ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
            FROM read_parquet(?, hive_partitioning=1)
        )
        WHERE rn = 1
    """
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, [part_globs]).fetchdf()
        except (duckdb.CatalogException, duckdb.IOException):
            return {}

    if rows.empty:
        return {}

    rows = rows.where(pd.notna(rows), None)
    result: dict[str, dict[str, object]] = {}
    for row in rows.to_dict(orient="records"):
        ts_code = row.pop("ts_code", None)
        if ts_code:
            result[ts_code] = row
    return result


def list_latest_daily_prices(ts_codes: list[str]) -> dict[str, dict[str, object]]:
    if not ts_codes:
        return {}

    daily_root = settings.data_dir / "raw" / "daily"
    if not daily_root.exists():
        return {}

    part_globs: list[str] = []
    for code in ts_codes:
        code_dir = daily_root / f"ts_code={code}"
        if code_dir.exists():
            part_globs.append(str(code_dir / "year=*/part-*.parquet"))
    if not part_globs:
        return {}

    query = """
        SELECT ts_code,
               trade_date,
               close,
               pre_close,
               COALESCE(pct_chg, (close - pre_close) / NULLIF(pre_close, 0) * 100) AS pct_chg
        FROM (
            SELECT ts_code,
                   trade_date,
                   close,
                   pre_close,
                   pct_chg,
                   ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
            FROM read_parquet(?, hive_partitioning=1)
        )
        WHERE rn = 1
    """
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, [part_globs]).fetchdf()
        except (duckdb.CatalogException, duckdb.IOException):
            return {}

    if rows.empty:
        return {}

    rows = rows.where(pd.notna(rows), None)
    result: dict[str, dict[str, object]] = {}
    for row in rows.to_dict(orient="records"):
        ts_code = str(row.get("ts_code") or "").strip().upper()
        if not ts_code:
            continue
        result[ts_code] = {
            "trade_date": row.get("trade_date"),
            "close": row.get("close"),
            "pre_close": row.get("pre_close"),
            "pct_chg": row.get("pct_chg"),
        }
    return result


def list_last_n_days_pct_chg(
    ts_codes: list[str], n: int = 3
) -> dict[str, dict[str, object]]:
    """近 N 个交易日涨跌幅合计，key 为 ts_code，value 含 pct_chg_3d（或 pct_chg_nd）。"""
    if not ts_codes or n < 1:
        return {}

    daily_root = settings.data_dir / "raw" / "daily"
    if not daily_root.exists():
        return {}

    part_globs: list[str] = []
    for code in ts_codes:
        code_dir = daily_root / f"ts_code={code}"
        if code_dir.exists():
            part_globs.append(str(code_dir / "year=*/part-*.parquet"))
    if not part_globs:
        return {}

    query = """
        SELECT ts_code,
               MAX(CASE WHEN rn = 1 THEN pct_chg END) AS pct_chg_1,
               MAX(CASE WHEN rn = 2 THEN pct_chg END) AS pct_chg_2,
               MAX(CASE WHEN rn = 3 THEN pct_chg END) AS pct_chg_3,
               MAX(CASE WHEN rn = 4 THEN pct_chg END) AS pct_chg_4,
               MAX(CASE WHEN rn = 5 THEN pct_chg END) AS pct_chg_5,
               MAX(CASE WHEN rn = 1 THEN trade_date END) AS trade_date_1,
               MAX(CASE WHEN rn = 2 THEN trade_date END) AS trade_date_2,
               MAX(CASE WHEN rn = 3 THEN trade_date END) AS trade_date_3,
               MAX(CASE WHEN rn = 4 THEN trade_date END) AS trade_date_4,
               MAX(CASE WHEN rn = 5 THEN trade_date END) AS trade_date_5,
               SUM(pct_chg) AS pct_chg_nd
        FROM (
            SELECT ts_code,
                   trade_date,
                   COALESCE(pct_chg, (close - pre_close) / NULLIF(pre_close, 0) * 100) AS pct_chg,
                   ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
            FROM read_parquet(?, hive_partitioning=1)
        )
        WHERE rn <= ?
        GROUP BY ts_code
    """
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, [part_globs, n]).fetchdf()
        except (duckdb.CatalogException, duckdb.IOException):
            return {}

    if rows.empty:
        return {}

    rows = rows.where(pd.notna(rows), None)
    result: dict[str, dict[str, object]] = {}
    for row in rows.to_dict(orient="records"):
        ts_code = row.pop("ts_code", None)
        if ts_code:
            result[ts_code] = {
                "pct_chg_nd": row.get("pct_chg_nd"),
                "pct_chg_1": row.get("pct_chg_1"),
                "pct_chg_2": row.get("pct_chg_2"),
                "pct_chg_3": row.get("pct_chg_3"),
                "pct_chg_4": row.get("pct_chg_4"),
                "pct_chg_5": row.get("pct_chg_5"),
                "pct_chg_1_date": row.get("trade_date_1"),
                "pct_chg_2_date": row.get("trade_date_2"),
                "pct_chg_3_date": row.get("trade_date_3"),
                "pct_chg_4_date": row.get("trade_date_4"),
                "pct_chg_5_date": row.get("trade_date_5"),
            }
    return result


def list_daily_changes_for_date(ts_codes: list[str], trade_date: str) -> dict[str, dict[str, object]]:
    if not ts_codes or not trade_date:
        return {}

    daily_root = settings.data_dir / "raw" / "daily"
    if not daily_root.exists():
        return {}

    part_globs: list[str] = []
    for code in ts_codes:
        code_dir = daily_root / f"ts_code={code}"
        if code_dir.exists():
            part_globs.append(str(code_dir / "year=*/part-*.parquet"))
    if not part_globs:
        return {}

    placeholders = ", ".join(["?"] * len(ts_codes))
    query = f"""
        SELECT ts_code,
               trade_date,
               COALESCE(change, close - pre_close) AS change,
               COALESCE(pct_chg, (close - pre_close) / NULLIF(pre_close, 0) * 100) AS pct_chg
        FROM read_parquet(?, hive_partitioning=1)
        WHERE trade_date = ? AND ts_code IN ({placeholders})
    """
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, [part_globs, trade_date, *ts_codes]).fetchdf()
        except (duckdb.CatalogException, duckdb.IOException):
            return {}

    if rows.empty:
        return {}

    rows = rows.where(pd.notna(rows), None)
    result: dict[str, dict[str, object]] = {}
    for row in rows.to_dict(orient="records"):
        ts_code = row.pop("ts_code", None)
        if ts_code:
            result[ts_code] = row
    return result


def get_next_trade_date(ts_codes: list[str], trade_date: str) -> str | None:
    if not ts_codes or not trade_date:
        return None

    daily_root = settings.data_dir / "raw" / "daily"
    if not daily_root.exists():
        return None

    part_globs: list[str] = []
    for code in ts_codes:
        code_dir = daily_root / f"ts_code={code}"
        if code_dir.exists():
            part_globs.append(str(code_dir / "year=*/part-*.parquet"))
    if not part_globs:
        return None

    query = """
        SELECT MIN(trade_date) AS next_trade_date
        FROM read_parquet(?, hive_partitioning=1)
        WHERE trade_date > ?
    """
    with get_connection(read_only=True) as con:
        try:
            row = con.execute(query, [part_globs, trade_date]).fetchone()
        except (duckdb.CatalogException, duckdb.IOException):
            return None
    if not row:
        return None
    return row[0] or None
