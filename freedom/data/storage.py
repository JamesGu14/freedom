from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Sequence

from .models import BasicInfo, DailyBar


class SQLiteStorage:
    """
    SQLite-backed storage for basic info and daily bars.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS basic_info (
                ts_code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market TEXT NOT NULL,
                list_date TEXT NOT NULL,
                is_active INTEGER NOT NULL,
                industry TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_bars (
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                pre_close REAL NOT NULL,
                pct_chg REAL NOT NULL,
                vol REAL NOT NULL,
                amount REAL NOT NULL,
                turnover_rate REAL,
                PRIMARY KEY (ts_code, trade_date)
            );
            """
        )
        self._conn.commit()

    def upsert_basic_info(self, infos: Sequence[BasicInfo]) -> int:
        if not infos:
            return 0
        cur = self._conn.cursor()
        cur.executemany(
            """
            INSERT INTO basic_info (ts_code, name, market, list_date, is_active, industry)
            VALUES (:ts_code, :name, :market, :list_date, :is_active, :industry)
            ON CONFLICT(ts_code) DO UPDATE SET
                name=excluded.name,
                market=excluded.market,
                list_date=excluded.list_date,
                is_active=excluded.is_active,
                industry=excluded.industry;
            """,
            [
                {
                    "ts_code": info.ts_code,
                    "name": info.name,
                    "market": info.market,
                    "list_date": info.list_date.isoformat(),
                    "is_active": 1 if info.is_active else 0,
                    "industry": info.industry,
                }
                for info in infos
            ],
        )
        self._conn.commit()
        return cur.rowcount

    def upsert_daily_bars(self, bars: Sequence[DailyBar]) -> int:
        if not bars:
            return 0
        cur = self._conn.cursor()
        cur.executemany(
            """
            INSERT INTO daily_bars (
                ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount, turnover_rate
            )
            VALUES (
                :ts_code, :trade_date, :open, :high, :low, :close, :pre_close, :pct_chg, :vol, :amount, :turnover_rate
            )
            ON CONFLICT(ts_code, trade_date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                pre_close=excluded.pre_close,
                pct_chg=excluded.pct_chg,
                vol=excluded.vol,
                amount=excluded.amount,
                turnover_rate=excluded.turnover_rate;
            """,
            [
                {
                    "ts_code": bar.ts_code,
                    "trade_date": bar.trade_date.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "pre_close": bar.pre_close,
                    "pct_chg": bar.pct_chg,
                    "vol": bar.vol,
                    "amount": bar.amount,
                    "turnover_rate": bar.turnover_rate,
                }
                for bar in bars
            ],
        )
        self._conn.commit()
        return cur.rowcount

    def fetch_basic_info(self) -> List[BasicInfo]:
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT ts_code, name, market, list_date, is_active, industry FROM basic_info"
        ).fetchall()
        return [
            BasicInfo(
                ts_code=row["ts_code"],
                name=row["name"],
                market=row["market"],
                list_date=_parse_date(row["list_date"]),
                is_active=bool(row["is_active"]),
                industry=row["industry"],
            )
            for row in rows
        ]

    def fetch_daily_bars(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> List[DailyBar]:
        cur = self._conn.cursor()
        query = "SELECT * FROM daily_bars WHERE ts_code = :ts_code"
        params: dict = {"ts_code": ts_code}
        if start_date:
            query += " AND trade_date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            query += " AND trade_date <= :end_date"
            params["end_date"] = end_date
        query += " ORDER BY trade_date ASC"
        rows = cur.execute(query, params).fetchall()
        return [
            DailyBar(
                ts_code=row["ts_code"],
                trade_date=_parse_date(row["trade_date"]),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                pre_close=row["pre_close"],
                pct_chg=row["pct_chg"],
                vol=row["vol"],
                amount=row["amount"],
                turnover_rate=row["turnover_rate"],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()


def _parse_date(value: str) -> "date":
    from datetime import date

    return date.fromisoformat(value)
