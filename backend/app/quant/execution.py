from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.quant.portfolio import PortfolioState, Position


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number


def build_price_maps(next_daily_df: pd.DataFrame, next_limit_df: pd.DataFrame) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    price_map: dict[str, dict[str, float]] = {}
    limit_map: dict[str, dict[str, float]] = {}
    if next_daily_df is not None and not next_daily_df.empty:
        for row in next_daily_df.to_dict(orient="records"):
            ts_code = str(row.get("ts_code") or "")
            if not ts_code:
                continue
            price_map[ts_code] = {
                "open": _to_float(row.get("open")),
                "close": _to_float(row.get("close")),
            }
    if next_limit_df is not None and not next_limit_df.empty:
        for row in next_limit_df.to_dict(orient="records"):
            ts_code = str(row.get("ts_code") or "")
            if not ts_code:
                continue
            limit_map[ts_code] = {
                "up_limit": _to_float(row.get("up_limit")),
                "down_limit": _to_float(row.get("down_limit")),
            }
    return price_map, limit_map


def _is_buy_blocked(open_price: float, up_limit: float) -> bool:
    if up_limit <= 0:
        return False
    return open_price >= up_limit


def _is_sell_blocked(open_price: float, down_limit: float) -> bool:
    if down_limit <= 0:
        return False
    return open_price <= down_limit


def _buy_qty_from_amount(target_amount: float, open_price: float) -> int:
    if target_amount <= 0 or open_price <= 0:
        return 0
    return int(math.floor(target_amount / open_price / 100.0) * 100)


def execute_orders(
    *,
    run_id: str,
    signal_trade_date: str,
    execution_trade_date: str,
    portfolio: PortfolioState,
    orders: list[dict[str, Any]],
    next_daily_df: pd.DataFrame,
    next_limit_df: pd.DataFrame,
    trade_index: int,
) -> list[dict[str, Any]]:
    price_map, limit_map = build_price_maps(next_daily_df, next_limit_df)
    trades: list[dict[str, Any]] = []
    if not orders:
        return trades

    sell_orders = [item for item in orders if str(item.get("side")) == "SELL"]
    buy_orders = [item for item in orders if str(item.get("side")) == "BUY"]

    cancelled_groups: set[str] = set()
    for order in sell_orders:
        ts_code = str(order.get("ts_code") or "")
        if ts_code not in portfolio.positions:
            continue
        position = portfolio.positions[ts_code]
        px = price_map.get(ts_code, {})
        open_price = _to_float(px.get("open"))
        limits = limit_map.get(ts_code, {})
        down_limit = _to_float(limits.get("down_limit"))
        can_trade_reason = "ok"
        if open_price <= 0:
            can_trade_reason = "missing_open_price"
        elif _is_sell_blocked(open_price, down_limit):
            can_trade_reason = "limit_down_blocked"
        if can_trade_reason != "ok":
            group_id = str(order.get("rotate_group") or "")
            if group_id:
                cancelled_groups.add(group_id)
            continue

        qty = int(position.qty)
        amount = qty * open_price
        realized_pnl = (open_price - float(position.cost_price)) * qty
        portfolio.cash += amount
        del portfolio.positions[ts_code]
        trades.append(
            {
                "run_id": run_id,
                "trade_date": execution_trade_date,
                "signal_trade_date": signal_trade_date,
                "ts_code": ts_code,
                "side": "SELL",
                "signal_type": order.get("signal_type", "SELL"),
                "price": open_price,
                "qty": qty,
                "amount": amount,
                "cost_price": float(position.cost_price),
                "realized_pnl": realized_pnl,
                "fee": 0.0,
                "slippage_cost": 0.0,
                "score": _to_float(order.get("score")),
                "target_weight": _to_float(order.get("target_weight")),
                "target_amount": _to_float(order.get("target_amount")),
                "reason_codes": list(order.get("reason_codes") or []),
                "can_trade_reason": can_trade_reason,
                "trade_index": trade_index,
                "trade_uid": f"{run_id}:{execution_trade_date}:{ts_code}:SELL:{qty}",
            }
        )

    for order in buy_orders:
        ts_code = str(order.get("ts_code") or "")
        if ts_code in portfolio.positions:
            continue
        group_id = str(order.get("rotate_group") or "")
        if group_id and group_id in cancelled_groups:
            continue
        px = price_map.get(ts_code, {})
        open_price = _to_float(px.get("open"))
        limits = limit_map.get(ts_code, {})
        up_limit = _to_float(limits.get("up_limit"))
        can_trade_reason = "ok"
        if open_price <= 0:
            can_trade_reason = "missing_open_price"
        elif _is_buy_blocked(open_price, up_limit):
            can_trade_reason = "limit_up_blocked"
        if can_trade_reason != "ok":
            continue

        target_amount = _to_float(order.get("target_amount"))
        qty = _buy_qty_from_amount(target_amount, open_price)
        if qty <= 0:
            continue
        max_affordable = _buy_qty_from_amount(portfolio.cash, open_price)
        qty = min(qty, max_affordable)
        if qty <= 0:
            continue

        amount = qty * open_price
        portfolio.cash -= amount
        portfolio.positions[ts_code] = Position(
            ts_code=ts_code,
            qty=qty,
            cost_price=open_price,
            buy_trade_date=execution_trade_date,
            buy_trade_index=trade_index,
            max_price=open_price,
        )
        trades.append(
            {
                "run_id": run_id,
                "trade_date": execution_trade_date,
                "signal_trade_date": signal_trade_date,
                "ts_code": ts_code,
                "side": "BUY",
                "signal_type": order.get("signal_type", "BUY"),
                "price": open_price,
                "qty": qty,
                "amount": amount,
                "fee": 0.0,
                "slippage_cost": 0.0,
                "score": _to_float(order.get("score")),
                "target_weight": _to_float(order.get("target_weight")),
                "target_amount": target_amount,
                "reason_codes": list(order.get("reason_codes") or []),
                "can_trade_reason": can_trade_reason,
                "trade_index": trade_index,
                "trade_uid": f"{run_id}:{execution_trade_date}:{ts_code}:BUY:{qty}",
            }
        )

    return trades
