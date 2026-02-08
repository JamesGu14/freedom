from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Position:
    ts_code: str
    qty: int
    cost_price: float
    buy_trade_date: str
    buy_trade_index: int
    max_price: float


@dataclass
class PortfolioState:
    initial_capital: float
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        if value is None or value == "":
            return default
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        return number

    def total_position_value(self, close_map: dict[str, float]) -> float:
        total = 0.0
        for ts_code, position in self.positions.items():
            close = self._safe_float(close_map.get(ts_code), 0.0)
            total += position.qty * close
        return total

    def total_equity(self, close_map: dict[str, float]) -> float:
        cash = self._safe_float(self.cash, 0.0)
        return cash + self.total_position_value(close_map)

    def update_max_price(self, close_map: dict[str, float]) -> None:
        for ts_code, position in list(self.positions.items()):
            close = self._safe_float(close_map.get(ts_code), 0.0)
            if close <= 0:
                continue
            if close > position.max_price:
                position.max_price = close

    def holding_count(self) -> int:
        return len(self.positions)

    def to_positions_snapshot(
        self,
        *,
        run_id: str,
        trade_date: str,
        close_map: dict[str, float],
        score_map: dict[str, float] | None = None,
        trade_index_map: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        score_map = score_map or {}
        trade_index_map = trade_index_map or {}
        total_equity = self.total_equity(close_map)
        snapshots: list[dict[str, Any]] = []
        trade_index = trade_index_map.get(trade_date, 0)
        for ts_code, position in self.positions.items():
            close = self._safe_float(close_map.get(ts_code), 0.0)
            market_value = close * position.qty
            pnl = (close - position.cost_price) * position.qty
            weight = market_value / total_equity if total_equity > 0 else 0.0
            holding_days = max(trade_index - position.buy_trade_index, 0)
            snapshots.append(
                {
                    "run_id": run_id,
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "shares": position.qty,
                    "cost_price": position.cost_price,
                    "market_price": close,
                    "market_value": market_value,
                    "pnl": pnl,
                    "weight": weight,
                    "holding_days": holding_days,
                    "score": self._safe_float(score_map.get(ts_code), 0.0),
                }
            )
        return snapshots
