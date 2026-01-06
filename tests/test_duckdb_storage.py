import importlib.util
import os
import tempfile
import unittest
from datetime import date

from freedom.data.models import BasicInfo, DailyBar

duckdb_spec = importlib.util.find_spec("duckdb")


@unittest.skipIf(duckdb_spec is None, "duckdb not installed in environment")
class DuckDBStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        from freedom.data.storage_duckdb import DuckDBStorage

        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmpdir.name, "data.duckdb")
        parquet_dir = os.path.join(self.tmpdir.name, "parquet")
        self.storage = DuckDBStorage(db_path, parquet_dir)

    def tearDown(self) -> None:
        self.storage.close()
        self.tmpdir.cleanup()

    def test_upsert_and_fetch(self):
        info = BasicInfo(
            ts_code="000001.SZ",
            name="Ping An Bank",
            market="SZ",
            list_date=date(1991, 4, 3),
            is_active=True,
            industry="Banking",
        )
        bar = DailyBar(
            ts_code="000001.SZ",
            trade_date=date(2024, 1, 10),
            open=10.0,
            high=10.5,
            low=9.8,
            close=10.3,
            pre_close=9.9,
            pct_chg=4.04,
            vol=1000000,
            amount=10200000.0,
            turnover_rate=1.0,
        )
        self.storage.upsert_basic_info([info])
        self.storage.upsert_daily_bars([bar])

        fetched_info = self.storage.fetch_basic_info()
        self.assertEqual(fetched_info[0].ts_code, "000001.SZ")

        fetched_bars = self.storage.fetch_daily_bars("000001.SZ")
        self.assertEqual(len(fetched_bars), 1)
        self.assertEqual(fetched_bars[0].close, 10.3)


if __name__ == "__main__":
    unittest.main()
