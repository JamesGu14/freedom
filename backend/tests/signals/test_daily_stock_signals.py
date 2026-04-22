from __future__ import annotations

import unittest

import pandas as pd

from app.signals.daily_stock_signals import (
    build_resonance_documents,
    build_signal_documents,
    classify_resonance_level,
    compute_signal_flags_for_stock,
    generate_daily_stock_signal_docs_for_range,
)


class ClassifyResonanceLevelTestCase(unittest.TestCase):
    def test_classifies_expected_levels(self) -> None:
        self.assertIsNone(classify_resonance_level(1))
        self.assertEqual("normal", classify_resonance_level(2))
        self.assertEqual("strong", classify_resonance_level(3))
        self.assertEqual("very_strong", classify_resonance_level(4))


class ComputeSignalFlagsForStockTestCase(unittest.TestCase):
    def test_buy_double_cross_requires_macd_and_kdj_cross_same_day(self) -> None:
        rows = [
            {
                "trade_date": "20260416",
                "close_qfq": 10.0,
                "volume_ratio": 1.0,
                "macd": 0.1,
                "macd_signal": 0.2,
                "kdj_k": 20.0,
                "kdj_d": 25.0,
                "ma5": 9.9,
                "ma10": 10.0,
                "ma20": 10.1,
                "ma60": 10.2,
                "rsi6": 25.0,
                "rsi12": 30.0,
            },
            {
                "trade_date": "20260417",
                "close_qfq": 10.5,
                "volume_ratio": 1.6,
                "macd": 0.3,
                "macd_signal": 0.2,
                "kdj_k": 30.0,
                "kdj_d": 25.0,
                "ma5": 10.3,
                "ma10": 10.1,
                "ma20": 9.9,
                "ma60": 9.5,
                "rsi6": 31.0,
                "rsi12": 28.0,
            },
        ]

        result = compute_signal_flags_for_stock(rows, target_date="20260417")

        self.assertTrue(result["buy_macd_kdj_double_cross"])
        self.assertFalse(result["sell_macd_kdj_double_cross"])

    def test_buy_ma_bullish_formation_only_triggers_on_formation_day(self) -> None:
        rows = [
            {
                "trade_date": "20260416",
                "close_qfq": 10.0,
                "volume_ratio": 1.0,
                "macd": 0.1,
                "macd_signal": 0.2,
                "kdj_k": 20.0,
                "kdj_d": 25.0,
                "ma5": 10.0,
                "ma10": 9.9,
                "ma20": 10.1,
                "ma60": 9.5,
                "rsi6": 25.0,
                "rsi12": 30.0,
            },
            {
                "trade_date": "20260417",
                "close_qfq": 10.2,
                "volume_ratio": 1.0,
                "macd": 0.1,
                "macd_signal": 0.2,
                "kdj_k": 20.0,
                "kdj_d": 25.0,
                "ma5": 10.3,
                "ma10": 10.1,
                "ma20": 9.9,
                "ma60": 9.5,
                "rsi6": 25.0,
                "rsi12": 30.0,
            },
        ]

        result = compute_signal_flags_for_stock(rows, target_date="20260417")

        self.assertTrue(result["buy_ma_bullish_formation"])
        self.assertFalse(result["sell_ma_bearish_formation"])

    def test_breakout_uses_close_qfq_and_volume_ratio_threshold(self) -> None:
        rows = []
        for index in range(1, 21):
            rows.append(
                {
                    "trade_date": f"202604{index:02d}",
                    "close_qfq": 10.0 + (index * 0.01),
                    "volume_ratio": 1.0,
                    "macd": 0.0,
                    "macd_signal": 0.0,
                    "kdj_k": 20.0,
                    "kdj_d": 20.0,
                    "ma5": 10.0,
                    "ma10": 10.0,
                    "ma20": 10.0,
                    "ma60": 10.0,
                    "rsi6": 50.0,
                    "rsi12": 50.0,
                }
            )
        rows.append(
            {
                "trade_date": "20260421",
                "close_qfq": 10.8,
                "volume_ratio": 1.6,
                "macd": 0.0,
                "macd_signal": 0.0,
                "kdj_k": 20.0,
                "kdj_d": 20.0,
                "ma5": 10.0,
                "ma10": 10.0,
                "ma20": 10.0,
                "ma60": 10.0,
                "rsi6": 50.0,
                "rsi12": 50.0,
            }
        )

        result = compute_signal_flags_for_stock(rows, target_date="20260421")

        self.assertTrue(result["buy_volume_breakout_20d"])
        self.assertFalse(result["sell_volume_breakdown_20d"])


class BuildDocumentsTestCase(unittest.TestCase):
    def test_build_signal_documents_emits_all_signal_types_with_empty_groups(self) -> None:
        stock_rows = [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "industry": "银行",
                "close": 11.0,
                "pct_chg": 1.2,
                "volume_ratio": 1.8,
                "signal_count_same_side": {"buy": 2, "sell": 0},
                "signal_hits": {
                    "buy_macd_kdj_double_cross": True,
                    "buy_ma_bullish_formation": True,
                },
                "metrics": {
                    "buy_macd_kdj_double_cross": {"macd": 0.1, "macd_signal": 0.05, "kdj_k": 40.0, "kdj_d": 30.0},
                    "buy_ma_bullish_formation": {"ma5": 11.1, "ma10": 10.8, "ma20": 10.5, "ma60": 10.0},
                },
            }
        ]

        docs = build_signal_documents(trade_date="20260417", stock_rows=stock_rows)

        self.assertEqual(8, len(docs))
        by_type = {doc["signal_type"]: doc for doc in docs}
        self.assertEqual(1, by_type["buy_macd_kdj_double_cross"]["count"])
        self.assertEqual(1, by_type["buy_ma_bullish_formation"]["count"])
        self.assertEqual(0, by_type["sell_rsi_fall"]["count"])

    def test_build_resonance_documents_groups_by_side_and_level(self) -> None:
        stock_rows = [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "industry": "银行",
                "close": 11.0,
                "pct_chg": 1.2,
                "volume_ratio": 1.8,
                "signal_count_same_side": {"buy": 3, "sell": 0},
                "signal_hits": {
                    "buy_macd_kdj_double_cross": True,
                    "buy_ma_bullish_formation": True,
                    "buy_volume_breakout_20d": True,
                },
            }
        ]

        docs = build_resonance_documents(trade_date="20260417", stock_rows=stock_rows)

        self.assertEqual(6, len(docs))
        target = next(doc for doc in docs if doc["signal_side"] == "buy" and doc["resonance_level"] == "strong")
        self.assertEqual(1, target["count"])
        self.assertEqual(["buy_macd_kdj_double_cross", "buy_ma_bullish_formation", "buy_volume_breakout_20d"], target["stocks"][0]["signal_types"])


class GenerateDailyStockSignalDocsForRangeTestCase(unittest.TestCase):
    def test_range_generation_looks_up_stock_basics_once_for_multiple_target_dates(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260416",
                    "close": 10.0,
                    "pct_chg": 0.5,
                    "close_qfq": 10.0,
                    "ma5": 9.8,
                    "ma10": 9.9,
                    "ma20": 10.1,
                    "ma60": 10.2,
                    "macd": 0.1,
                    "macd_signal": 0.2,
                    "kdj_k": 20.0,
                    "kdj_d": 25.0,
                    "rsi6": 25.0,
                    "rsi12": 30.0,
                    "volume_ratio": 1.0,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260417",
                    "close": 10.5,
                    "pct_chg": 1.5,
                    "close_qfq": 10.5,
                    "ma5": 10.3,
                    "ma10": 10.1,
                    "ma20": 9.9,
                    "ma60": 9.5,
                    "macd": 0.3,
                    "macd_signal": 0.2,
                    "kdj_k": 30.0,
                    "kdj_d": 25.0,
                    "rsi6": 31.0,
                    "rsi12": 28.0,
                    "volume_ratio": 1.8,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260418",
                    "close": 10.7,
                    "pct_chg": 1.0,
                    "close_qfq": 10.7,
                    "ma5": 10.5,
                    "ma10": 10.2,
                    "ma20": 10.0,
                    "ma60": 9.6,
                    "macd": 0.35,
                    "macd_signal": 0.25,
                    "kdj_k": 32.0,
                    "kdj_d": 28.0,
                    "rsi6": 45.0,
                    "rsi12": 34.0,
                    "volume_ratio": 1.2,
                },
            ]
        )

        from app import signals as signals_pkg
        from app.signals import daily_stock_signals as module

        original_loader = module._load_joined_market_frame
        original_basics = module.get_stock_basic_map
        calls = {"basics": 0}
        try:
            module._load_joined_market_frame = lambda start_date, end_date: frame
            module.get_stock_basic_map = lambda ts_codes: calls.__setitem__("basics", calls["basics"] + 1) or {"000001.SZ": {"name": "平安银行", "industry": "银行"}}

            signal_docs, resonance_docs = generate_daily_stock_signal_docs_for_range(
                start_date="20260417",
                end_date="20260418",
                target_dates=["20260417", "20260418"],
            )
        finally:
            module._load_joined_market_frame = original_loader
            module.get_stock_basic_map = original_basics

        self.assertEqual(1, calls["basics"])
        self.assertEqual(16, len(signal_docs))
        self.assertEqual(12, len(resonance_docs))
        docs_for_0417 = [doc for doc in signal_docs if doc["trade_date"] == "20260417"]
        self.assertEqual(8, len(docs_for_0417))


if __name__ == "__main__":
    unittest.main()
