from datetime import date
import os
import tempfile
import unittest

from freedom.data.ingestor import DailyIngestor
from freedom.data.models import BasicInfo, DailyBar
from freedom.data.provider import InMemoryProvider
from freedom.data.storage import SQLiteStorage


class DailyIngestorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmpdir.name, "data.db")

        basic = [
            BasicInfo(
                ts_code="600000.SH",
                name="PF Bank",
                market="SH",
                list_date=date(1999, 11, 10),
                is_active=True,
                industry="Banking",
            )
        ]
        bars = [
            DailyBar(
                ts_code="600000.SH",
                trade_date=date(2024, 1, 10),
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                pre_close=9.9,
                pct_chg=3.03,
                vol=1200000,
                amount=12500000.5,
                turnover_rate=1.2,
            ),
            DailyBar(
                ts_code="600000.SH",
                trade_date=date(2024, 1, 11),
                open=10.2,
                high=10.8,
                low=10.0,
                close=10.6,
                pre_close=10.2,
                pct_chg=3.92,
                vol=1500000,
                amount=15800000.0,
                turnover_rate=1.4,
            ),
        ]

        self.provider = InMemoryProvider(basic_infos=basic, daily_bars=bars)
        self.storage = SQLiteStorage(db_path)
        self.ingestor = DailyIngestor(self.provider, self.storage)

    def tearDown(self) -> None:
        self.storage.close()
        self.tmpdir.cleanup()

    def test_ingest_basic_and_daily(self):
        result = self.ingestor.ingest(date(2024, 1, 10))
        self.assertEqual(result["basic_info"], 1)
        self.assertEqual(result["daily_bars"], 1)

        fetched_basic = self.storage.fetch_basic_info()
        self.assertEqual(len(fetched_basic), 1)
        self.assertEqual(fetched_basic[0].ts_code, "600000.SH")

        fetched_bars = self.storage.fetch_daily_bars("600000.SH")
        self.assertEqual(len(fetched_bars), 1)
        self.assertEqual(fetched_bars[0].close, 10.2)

    def test_upsert_overwrites_existing_data(self):
        self.ingestor.ingest(date(2024, 1, 10))
        updated_bar = DailyBar(
            ts_code="600000.SH",
            trade_date=date(2024, 1, 10),
            open=10.1,
            high=10.6,
            low=9.9,
            close=10.3,
            pre_close=9.9,
            pct_chg=4.04,
            vol=1300000,
            amount=13000000,
            turnover_rate=1.25,
        )

        updated_provider = InMemoryProvider(
            basic_infos=self.provider.basic_infos,
            daily_bars=[updated_bar],
        )
        ingestor = DailyIngestor(updated_provider, self.storage)
        ingestor.ingest(date(2024, 1, 10), refresh_basic_info=False)

        fetched_bars = self.storage.fetch_daily_bars("600000.SH")
        self.assertEqual(fetched_bars[0].open, 10.1)
        self.assertEqual(fetched_bars[0].pct_chg, 4.04)

    def test_validation_rejects_high_lower_than_low(self):
        invalid_bar = DailyBar(
            ts_code="600000.SH",
            trade_date=date(2024, 1, 12),
            open=10.5,
            high=10.0,
            low=10.1,
            close=10.2,
            pre_close=10.3,
            pct_chg=-0.97,
            vol=1100000,
            amount=11200000,
            turnover_rate=1.0,
        )
        provider = InMemoryProvider(
            basic_infos=self.provider.basic_infos,
            daily_bars=self.provider.daily_bars + [invalid_bar],
        )
        ingestor = DailyIngestor(provider, self.storage)
        with self.assertRaises(ValueError):
            ingestor.ingest(date(2024, 1, 12), refresh_basic_info=False)


if __name__ == "__main__":
    unittest.main()
