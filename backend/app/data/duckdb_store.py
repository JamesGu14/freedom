from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

from app.core.config import settings
from app.data.parquet_store import (
    get_parquet_pattern,
    write_adj_factor_to_parquet,
    write_daily_to_parquet,
    write_stock_basic_to_parquet,
)


def _register_parquet_tables(con: duckdb.DuckDBPyConnection) -> None:
    """将 Parquet 文件注册为外部表或视图"""
    parquet_base = settings.data_dir / "raw"

    # daily 表：使用 glob 模式读取所有日期分区
    daily_pattern = get_parquet_pattern("daily")
    daily_dir = parquet_base / "daily"
    if daily_dir.exists() and any(daily_dir.glob("trade_date=*")):
        try:
            con.execute(f"""
                CREATE OR REPLACE VIEW daily AS
                SELECT * FROM read_parquet('{daily_pattern}')
            """)
        except Exception:
            # 如果 Parquet 文件不存在，尝试使用表
            pass

    # adj_factor 表
    adj_pattern = get_parquet_pattern("adj_factor")
    adj_dir = parquet_base / "adj_factor"
    if adj_dir.exists() and any(adj_dir.glob("trade_date=*")):
        try:
            con.execute(f"""
                CREATE OR REPLACE VIEW adj_factor AS
                SELECT * FROM read_parquet('{adj_pattern}')
            """)
        except Exception:
            pass

    # stock_basic 表（小表，优先使用 Parquet）
    stock_basic_path = parquet_base / "stock_basic" / "part-0.parquet"
    if stock_basic_path.exists():
        try:
            con.execute(f"""
                CREATE OR REPLACE VIEW stock_basic AS
                SELECT * FROM read_parquet('{stock_basic_path}')
            """)
        except Exception:
            pass


logger = logging.getLogger(__name__)


def get_connection() -> duckdb.DuckDBPyConnection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # 添加配置以提升稳定性和性能
    try:
        con = duckdb.connect(
            str(settings.duckdb_path),
            config={
                "threads": 1,  # 单线程避免并发问题
                "enable_object_cache": False,  # 禁用对象缓存
            },
        )
    except Exception:
        logger.exception("DuckDB connect failed, falling back to in-memory database.")
        con = duckdb.connect(":memory:")
    # 注册 Parquet 文件为视图（如果 Parquet 文件存在）
    _register_parquet_tables(con)
    return con


def replace_stock_basic(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    # 写入 Parquet 文件
    write_stock_basic_to_parquet(df)

    # 同时保留 DuckDB 表（作为备份或兼容）
    with get_connection() as con:
        con.register("df", df)
        try:
            con.execute("CREATE OR REPLACE TABLE stock_basic AS SELECT * FROM df")
        except Exception:
            # 如果视图已存在，尝试删除视图后创建表
            try:
                con.execute("DROP VIEW IF EXISTS stock_basic")
                con.execute("CREATE TABLE stock_basic AS SELECT * FROM df")
            except Exception:
                pass
    return df.shape[0]


def list_stock_basic(
    *,
    page: int = 1,
    page_size: int = 10,
    name: str | None = None,
    ts_code: str | None = None,
    industry: str | None = None,
) -> tuple[list[dict[str, object]], int]:
    where_clauses: list[str] = []
    params: list[object] = []

    if name:
        where_clauses.append("name ILIKE ?")
        params.append(f"%{name}%")
    if ts_code:
        where_clauses.append("ts_code ILIKE ?")
        params.append(f"%{ts_code}%")
    if industry:
        where_clauses.append("industry = ?")
        params.append(industry)

    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    offset = max(page - 1, 0) * page_size

    query = (
        "SELECT ts_code, symbol, name, area, industry, market, list_date "
        "FROM stock_basic"
        f"{where_sql} "
        "ORDER BY ts_code "
        "LIMIT ? OFFSET ?"
    )
    count_query = f"SELECT COUNT(*) FROM stock_basic{where_sql}"
    with get_connection() as con:
        try:
            total = con.execute(count_query, params).fetchone()[0]
            rows = con.execute(query, params + [page_size, offset]).fetchdf()
        except duckdb.CatalogException:
            return [], 0
    return rows.to_dict(orient="records"), int(total)


def list_industries() -> list[str]:
    query = (
        "SELECT DISTINCT industry FROM stock_basic "
        "WHERE industry IS NOT NULL AND industry <> '' "
        "ORDER BY industry"
    )
    with get_connection() as con:
        try:
            rows = con.execute(query).fetchall()
        except duckdb.CatalogException:
            return []
    return [row[0] for row in rows]


def upsert_daily(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    # 写入 Parquet 文件（按日期分区）
    written = write_daily_to_parquet(df)

    # 刷新视图（Parquet 文件已更新，视图会自动读取新数据）
    # 如果还有旧的 DuckDB 表，也更新它（向后兼容）
    # 注意：由于现在使用 Parquet 视图，不需要再更新 DuckDB 表
    # 如果需要向后兼容，可以保留以下代码
    # with get_connection() as con:
    #     try:
    #         # 尝试直接插入（如果是表会成功，如果是视图会失败）
    #         con.register("df", df)
    #         con.execute(
    #             """
    #             INSERT INTO daily
    #             SELECT df.*
    #             FROM df
    #             LEFT JOIN daily d
    #               ON d.ts_code = df.ts_code AND d.trade_date = df.trade_date
    #             WHERE d.ts_code IS NULL
    #             """
    #         )
    #     except Exception:
    #         # 视图不支持 INSERT，忽略
    #         pass

    return written


def upsert_adj_factor(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    # 写入 Parquet 文件（按日期分区）
    written = write_adj_factor_to_parquet(df)

    # 刷新视图（Parquet 文件已更新，视图会自动读取新数据）
    # 如果还有旧的 DuckDB 表，也更新它（向后兼容）
    # 注意：由于现在使用 Parquet 视图，不需要再更新 DuckDB 表
    # 如果需要向后兼容，可以保留以下代码
    # with get_connection() as con:
    #     try:
    #         con.register("df", df)
    #         con.execute(
    #             """
    #             INSERT INTO adj_factor
    #             SELECT df.*
    #             FROM df
    #             LEFT JOIN adj_factor a
    #               ON a.ts_code = df.ts_code AND a.trade_date = df.trade_date
    #             WHERE a.ts_code IS NULL
    #             """
    #         )
    #     except Exception:
    #         # 视图不支持 INSERT，忽略
    #         pass

    return written


def list_daily(ts_code: str) -> list[dict[str, object]]:
    query = (
        "SELECT ts_code, trade_date, open, high, low, close, vol, amount "
        "FROM daily WHERE ts_code = ? ORDER BY trade_date"
    )
    with get_connection() as con:
        try:
            rows = con.execute(query, [ts_code]).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_adj_factor(ts_code: str) -> list[dict[str, object]]:
    query = (
        "SELECT ts_code, trade_date, adj_factor "
        "FROM adj_factor WHERE ts_code = ? ORDER BY trade_date"
    )
    with get_connection() as con:
        try:
            rows = con.execute(query, [ts_code]).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_features_daily(ts_code: str) -> list[dict[str, object]]:
    query = """
        SELECT
            ts_code,
            trade_date,
            ma_5,
            ma_10,
            ma_20,
            ma_30,
            ma_60,
            ma_120,
            ma_250,
            macd_dif,
            macd_dea,
            macd_hist,
            rsi_14,
            boll_mid,
            boll_upper,
            boll_lower,
            kdj_k,
            kdj_d,
            kdj_j
        FROM features_daily
        WHERE ts_code = ?
        ORDER BY trade_date
    """
    with get_connection() as con:
        try:
            rows = con.execute(query, [ts_code]).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def get_stock_basic_by_code(ts_code: str) -> dict[str, object] | None:
    query = (
        "SELECT ts_code, name, industry, market "
        "FROM stock_basic WHERE ts_code = ? LIMIT 1"
    )
    with get_connection() as con:
        try:
            row = con.execute(query, [ts_code]).fetchone()
        except duckdb.CatalogException:
            return None
    if not row:
        return None
    return {"ts_code": row[0], "name": row[1], "industry": row[2], "market": row[3]}


def get_daily_with_adj(ts_code: str) -> pd.DataFrame:
    query = (
        "SELECT d.ts_code, d.trade_date, d.open, d.high, d.low, d.close, "
        "d.vol, d.amount, a.adj_factor "
        "FROM daily d "
        "LEFT JOIN adj_factor a "
        "ON d.ts_code = a.ts_code AND d.trade_date = a.trade_date "
        "WHERE d.ts_code = ? "
        "ORDER BY d.trade_date"
    )
    with get_connection() as con:
        try:
            return con.execute(query, [ts_code]).fetchdf()
        except duckdb.CatalogException:
            return pd.DataFrame()


def replace_features_daily(ts_code: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    with get_connection() as con:
        con.register("df", df)
        con.execute("CREATE TABLE IF NOT EXISTS features_daily AS SELECT * FROM df WHERE 1=0")
        con.execute("DELETE FROM features_daily WHERE ts_code = ?", [ts_code])
        con.execute("INSERT INTO features_daily SELECT * FROM df")
        return df.shape[0]
