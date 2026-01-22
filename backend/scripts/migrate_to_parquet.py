#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_store import get_connection
from app.data.parquet_store import (
    write_adj_factor_to_parquet,
    write_daily_to_parquet,
    write_stock_basic_to_parquet,
)
import pandas as pd


def migrate_daily(batch_size: int = 100000) -> None:
    """迁移 daily 表数据到 Parquet"""
    print("开始迁移 daily 表...")
    with get_connection() as con:
        # 检查表是否存在（尝试查询，如果失败可能是视图或不存在）
        try:
            # 尝试查询表（如果是视图也能查询，但我们需要检查是否是真正的表）
            con.execute("SELECT 1 FROM daily LIMIT 1")
        except Exception:
            print("daily 表/视图不存在或无法访问，跳过迁移")
            return

        # 获取总行数
        try:
            total = con.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
            print(f"总共 {total} 行数据需要迁移")
        except Exception as exc:
            print(f"无法获取 daily 表行数: {exc}")
            return

        # 分批读取并写入 Parquet
        offset = 0
        migrated = 0
        while True:
            try:
                df = con.execute(
                    f"""
                    SELECT * FROM daily
                    ORDER BY trade_date, ts_code
                    LIMIT {batch_size} OFFSET {offset}
                    """
                ).fetchdf()

                if df.empty:
                    break

                written = write_daily_to_parquet(df)
                migrated += len(df)
                print(
                    f"已迁移 {migrated}/{total} 行 "
                    f"(offset={offset}, written={written})"
                )
                offset += batch_size

            except Exception as exc:
                print(f"迁移失败 (offset={offset}): {exc}")
                break

    print(f"daily 表迁移完成，共迁移 {migrated} 行")


def migrate_adj_factor(batch_size: int = 100000) -> None:
    """迁移 adj_factor 表数据到 Parquet"""
    print("开始迁移 adj_factor 表...")
    with get_connection() as con:
        try:
            con.execute("SELECT 1 FROM adj_factor LIMIT 1")
        except Exception:
            print("adj_factor 表/视图不存在或无法访问，跳过迁移")
            return

        try:
            total = con.execute("SELECT COUNT(*) FROM adj_factor").fetchone()[0]
            print(f"总共 {total} 行数据需要迁移")
        except Exception as exc:
            print(f"无法获取 adj_factor 表行数: {exc}")
            return

        offset = 0
        migrated = 0
        while True:
            try:
                df = con.execute(
                    f"""
                    SELECT * FROM adj_factor
                    ORDER BY trade_date, ts_code
                    LIMIT {batch_size} OFFSET {offset}
                    """
                ).fetchdf()

                if df.empty:
                    break

                written = write_adj_factor_to_parquet(df)
                migrated += len(df)
                print(
                    f"已迁移 {migrated}/{total} 行 "
                    f"(offset={offset}, written={written})"
                )
                offset += batch_size

            except Exception as exc:
                print(f"迁移失败 (offset={offset}): {exc}")
                break

    print(f"adj_factor 表迁移完成，共迁移 {migrated} 行")


def migrate_stock_basic() -> None:
    """迁移 stock_basic 表数据到 Parquet"""
    print("开始迁移 stock_basic 表...")
    with get_connection() as con:
        try:
            con.execute("SELECT 1 FROM stock_basic LIMIT 1")
        except Exception:
            print("stock_basic 表/视图不存在或无法访问，跳过迁移")
            return

        try:
            df = con.execute("SELECT * FROM stock_basic").fetchdf()
            if df.empty:
                print("stock_basic 表为空，跳过迁移")
                return

            written = write_stock_basic_to_parquet(df)
            print(f"stock_basic 表迁移完成，共迁移 {written} 行")
        except Exception as exc:
            print(f"迁移 stock_basic 失败: {exc}")


def main() -> None:
    """主函数：迁移所有表"""
    print("=" * 60)
    print("开始将 DuckDB 数据迁移到 Parquet 文件")
    print("=" * 60)

    migrate_stock_basic()
    print()

    migrate_daily()
    print()

    migrate_adj_factor()
    print()

    print("=" * 60)
    print("迁移完成！")
    print("=" * 60)
    print()
    print("注意：")
    print("1. 数据已写入 Parquet 文件")
    print("2. DuckDB 中的表仍然保留（作为备份）")
    print("3. 新的查询将自动使用 Parquet 视图")
    print("4. 如果确认 Parquet 数据正确，可以删除 DuckDB 中的旧表")


if __name__ == "__main__":
    main()

