from __future__ import annotations

from app.services.daily_stock_signals_service import get_daily_stock_signals_overview


def test_overview_defaults_to_latest_date_and_limits_to_top_n(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.daily_stock_signals_service.list_daily_stock_signal_dates",
        lambda limit=365: ["20260417", "20260416"],
    )
    monkeypatch.setattr(
        "app.services.daily_stock_signals_service.list_signal_groups_for_date",
        lambda trade_date, signal_side=None: [
            {
                "trade_date": trade_date,
                "signal_type": "buy_macd_kdj_double_cross",
                "signal_side": "buy",
                "count": 2,
                "stocks": [{"ts_code": "000001.SZ"}, {"ts_code": "000002.SZ"}],
            },
            {
                "trade_date": trade_date,
                "signal_type": "sell_rsi_fall",
                "signal_side": "sell",
                "count": 1,
                "stocks": [{"ts_code": "000003.SZ"}],
            },
        ],
    )
    monkeypatch.setattr(
        "app.services.daily_stock_signals_service.list_resonance_groups_for_date",
        lambda trade_date, signal_side=None: [
            {
                "trade_date": trade_date,
                "signal_side": "buy",
                "resonance_level": "normal",
                "count": 1,
                "stocks": [{"ts_code": "000001.SZ"}, {"ts_code": "000002.SZ"}],
            }
        ],
    )

    result = get_daily_stock_signals_overview(top_n=1)

    assert result["trade_date"] == "20260417"
    assert len(result["buy_signals"][0]["stocks"]) == 1
    assert len(result["buy_resonance"][0]["stocks"]) == 1
