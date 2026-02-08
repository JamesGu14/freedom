from __future__ import annotations

from collections import defaultdict
from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _year(date_text: str) -> str:
    return str(date_text)[:4]


def calc_drawdown(nav_values: list[float]) -> list[float]:
    max_nav = 0.0
    draws: list[float] = []
    for nav in nav_values:
        max_nav = max(max_nav, nav)
        if max_nav <= 0:
            draws.append(0.0)
            continue
        draws.append((nav - max_nav) / max_nav)
    return draws


def build_summary_metrics(
    *,
    nav_rows: list[dict[str, Any]],
    initial_capital: float,
    trades: list[dict[str, Any]],
    benchmark_start: float | None = None,
    benchmark_end: float | None = None,
) -> dict[str, Any]:
    if not nav_rows:
        return {
            "total_return": 0.0,
            "annual_returns": {},
            "annual_max_drawdowns": {},
            "start_nav": 1.0,
            "end_nav": 1.0,
            "benchmark_total_return": 0.0,
            "trade_count": 0,
            "win_rate": 0.0,
        }

    sorted_rows = sorted(nav_rows, key=lambda x: str(x.get("trade_date") or ""))
    start_nav = _to_float(sorted_rows[0].get("nav"), 1.0)
    end_nav = _to_float(sorted_rows[-1].get("nav"), 1.0)
    total_return = end_nav - 1.0

    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted_rows:
        trade_date = str(row.get("trade_date") or "")
        if not trade_date:
            continue
        by_year[_year(trade_date)].append(row)

    annual_returns: dict[str, float] = {}
    annual_max_drawdowns: dict[str, float] = {}
    for year, items in sorted(by_year.items()):
        begin = _to_float(items[0].get("nav"), 1.0)
        finish = _to_float(items[-1].get("nav"), 1.0)
        if begin > 0:
            annual_returns[year] = finish / begin - 1.0
        else:
            annual_returns[year] = 0.0
        nav_values = [_to_float(item.get("nav"), 0.0) for item in items]
        annual_max_drawdowns[year] = min(calc_drawdown(nav_values) or [0.0])

    sell_trades = [item for item in trades if str(item.get("side")) == "SELL"]
    win_count = 0
    for row in sell_trades:
        realized_pnl = _to_float(row.get("realized_pnl"))
        if realized_pnl == 0.0:
            qty = _to_float(row.get("qty"))
            price = _to_float(row.get("price"))
            cost_price = _to_float(row.get("cost_price"))
            if qty > 0 and price > 0 and cost_price > 0:
                realized_pnl = (price - cost_price) * qty
        if realized_pnl > 0:
            win_count += 1
    win_rate = (win_count / len(sell_trades)) if sell_trades else 0.0

    benchmark_total_return = 0.0
    if benchmark_start and benchmark_end and benchmark_start > 0:
        benchmark_total_return = benchmark_end / benchmark_start - 1.0

    return {
        "total_return": total_return,
        "annual_returns": annual_returns,
        "annual_max_drawdowns": annual_max_drawdowns,
        "start_nav": start_nav,
        "end_nav": end_nav,
        "benchmark_total_return": benchmark_total_return,
        "trade_count": len(trades),
        "win_rate": win_rate,
        "initial_capital": initial_capital,
    }
