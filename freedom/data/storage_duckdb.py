from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterable, List, Sequence

from .models import BasicInfo, DailyBar

try:
    import duckdb
except ImportError as exc:  # pragma: no cover - handled in tests
    duckdb = None
    _duckdb_import_error = exc
else:
    _duckdb_import_error = None


class DuckDBStorage:
    """
    DuckDB-backed storage using Parquet as the physical layout.
    """

    def __init__(self, db_path: str | Path, data_dir: str | Path):
        if duckdb is None:
            raise ImportError(
                "duckdb is required for DuckDBStorage. "
                "Install via `pip install duckdb` or use SQLiteStorage instead."
            ) from _duckdb_import_error

        self.db_path = Path(db_path)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.db_path))
        self.init_schema()

    def init_schema(self) -> None:
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS basic_info (
                ts_code TEXT PRIMARY KEY,
                name TEXT,
                market TEXT,
                list_date DATE,
                is_active BOOLEAN,
                industry TEXT
            );
            """
        )
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_bars (
                ts_code TEXT,
                trade_date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                pre_close DOUBLE,
                pct_chg DOUBLE,
                vol DOUBLE,
                amount DOUBLE,
                turnover_rate DOUBLE,
                PRIMARY KEY (ts_code, trade_date)
            );
            """
        )
        self.con.commit()

    def upsert_basic_info(self, infos: Sequence[BasicInfo]) -> int:
        if not infos:
            return 0
        values = [
            (
                info.ts_code,
                info.name,
                info.market,
                info.list_date,
                info.is_active,
                info.industry,
            )
            for info in infos
        ]
        self.con.execute(
            """
            INSERT OR REPLACE INTO basic_info
            (ts_code, name, market, list_date, is_active, industry)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.con.commit()
        return len(values)

    def upsert_daily_bars(self, bars: Sequence[DailyBar]) -> int:
        if not bars:
            return 0
        values = [
            (
                bar.ts_code,
                bar.trade_date,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.pre_close,
                bar.pct_chg,
                bar.vol,
                bar.amount,
                bar.turnover_rate,
            )
            for bar in bars
        ]
        self.con.execute(
            """
            INSERT OR REPLACE INTO daily_bars (
                ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount, turnover_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.con.commit()
        return len(values)

    def export_parquet(self) -> None:
        """
        Export tables to partitioned Parquet files (year-based) for external use.
        """

        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Partition by year for daily bars
        self.con.execute(
            f"""
            COPY (
                SELECT * FROM daily_bars
            )
            TO '{self.data_dir / "daily_bars"}'
            (FORMAT PARQUET, PARTITION_BY (strftime(trade_date, '%Y')));
            """
        )
        self.con.execute(
            f"""
            COPY basic_info TO '{self.data_dir / "basic_info.parquet"}' (FORMAT PARQUET);
            """
        )
        self.con.commit()

    def fetch_basic_info(self) -> List[BasicInfo]:
        rows = self.con.execute(
            "SELECT ts_code, name, market, list_date, is_active, industry FROM basic_info"
        ).fetchall()
        return [
            BasicInfo(
                ts_code=row[0],
                name=row[1],
                market=row[2],
                list_date=row[3],
                is_active=bool(row[4]),
                industry=row[5],
            )
            for row in rows
        ]

    def fetch_daily_bars(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> List[DailyBar]:
        query = "SELECT * FROM daily_bars WHERE ts_code = ?"
        params: list = [ts_code]
        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        query += " ORDER BY trade_date ASC"
        rows = self.con.execute(query, params).fetchall()
        return [
            DailyBar(
                ts_code=row[0],
                trade_date=row[1],
                open=row[2],
                high=row[3],
                low=row[4],
                close=row[5],
                pre_close=row[6],
                pct_chg=row[7],
                vol=row[8],
                amount=row[9],
                turnover_rate=row[10],
            )
            for row in rows
        ]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.con.close()
