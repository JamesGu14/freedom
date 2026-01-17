from __future__ import annotations

import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_store import get_connection, list_daily, list_stk_limit  # noqa: E402
from app.core.config import settings  # noqa: E402
from scripts.strategy.second import EarlyBreakoutSignalModel  # noqa: E402
from scripts.strategy.third import DailySignalModel  # noqa: E402


STRATEGY_MAP = {
    "second": EarlyBreakoutSignalModel,
    "third": DailySignalModel,
}


class RegressionTest:
    def __init__(self, strategy_cls=DailySignalModel, initial_cash: float = 1_000_000.0):
        self.strategy_cls = strategy_cls
        self.initial_cash = float(initial_cash)
        self.logger = logging.getLogger(self.__class__.__name__)

    def _load_daily(self, stock_code: str) -> pd.DataFrame:
        ts_code = self._resolve_ts_code(stock_code)
        rows = list_daily(ts_code)
        if not rows:
            raise SystemExit(f"no daily data for {ts_code}")
        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        return df.sort_values("trade_date").reset_index(drop=True)

    def _load_limits(self, stock_code: str) -> dict[pd.Timestamp, dict[str, float]]:
        ts_code = self._resolve_ts_code(stock_code)
        try:
            rows = list_stk_limit(ts_code)
            if not rows:
                return {}
            df = pd.DataFrame(rows)
        except Exception:
            daily_limit_root = settings.data_dir / "raw" / "daily_limit" / f"ts_code={ts_code}"
            if not daily_limit_root.exists():
                return {}
            part_glob = str(daily_limit_root / "year=*/part-*.parquet")
            query = "SELECT * FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date"
            with duckdb.connect() as con:
                df = con.execute(query, [part_glob, ts_code]).fetchdf()
            if df.empty:
                return {}

        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        up_col = "up_limit" if "up_limit" in df.columns else None
        down_col = "down_limit" if "down_limit" in df.columns else None
        limits: dict[pd.Timestamp, dict[str, float]] = {}
        for row in df.itertuples(index=False):
            up_val = getattr(row, up_col) if up_col else None
            down_val = getattr(row, down_col) if down_col else None
            limits[row.trade_date] = {"up_limit": up_val, "down_limit": down_val}
        return limits

    def _resolve_ts_code(self, stock_code: str) -> str:
        if "." in stock_code:
            return stock_code
        with get_connection() as con:
            row = con.execute(
                "SELECT ts_code FROM stock_basic WHERE symbol = ? LIMIT 1",
                [stock_code],
            ).fetchone()
        if not row:
            return stock_code
        return row[0]

    def _list_stock_symbols(self) -> list[str]:
        with get_connection() as con:
            rows = con.execute(
                "SELECT symbol FROM stock_basic "
                "WHERE symbol LIKE '600%' OR symbol LIKE '000%' OR symbol LIKE '300%' "
                "ORDER BY symbol"
            ).fetchall()
        return [row[0] for row in rows]

    def test(
        self,
        stock_code: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        initial_cash: float | None = None,
    ) -> float:
        cash = float(self.initial_cash if initial_cash is None else initial_cash)
        shares = 0.0

        ts_code = self._resolve_ts_code(stock_code)
        model = self.strategy_cls(ts_code)
        if model.df is None or model.df.empty:
            logging.error("no data for %s", ts_code)
            return 0.0
        daily_df = self._load_daily(ts_code)
        limits = self._load_limits(ts_code)

        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)

        daily_df = daily_df[(daily_df["trade_date"] >= start_ts) & (daily_df["trade_date"] <= end_ts)]

        for row in daily_df.itertuples(index=False):
            date = row.trade_date
            close = row.close
            limit = limits.get(date)
            up_limit = None if limit is None else limit.get("up_limit")
            down_limit = None if limit is None else limit.get("down_limit")

            signal = model.predict_date(date)

            if signal == "BUY" and cash > 0:
                if up_limit is None or close < up_limit:
                    lot_shares = int(cash // (close * 100)) * 100
                    if lot_shares > 0:
                        cash_before = cash
                        shares = float(lot_shares)
                        cash = cash - shares * close
                        position_value = shares * close
                        self.logger.info(
                            "BUY %s %s price=%.4f shares=%.0f position_value=%.2f cash=%.2f",
                            stock_code,
                            date.date(),
                            close,
                            shares,
                            position_value,
                            cash,
                        )
            elif signal == "SELL" and shares > 0:
                if down_limit is None or close > down_limit:
                    position_value = shares * close
                    self.logger.info(
                        "SELL %s %s price=%.4f shares=%.0f position_value=%.2f cash=%.2f",
                        stock_code,
                        date.date(),
                        close,
                        shares,
                        position_value,
                        cash + position_value,
                    )
                    cash = shares * close
                    shares = 0.0

        initial = float(self.initial_cash if initial_cash is None else initial_cash)
        last_close = float(daily_df.iloc[-1]["close"]) if not daily_df.empty else 0.0
        position_value = shares * last_close
        equity = cash + position_value
        profit = equity - initial
        return_rate = (equity / initial - 1.0) if initial > 0 else 0.0
        logging.info("--------------------------------")
        logging.info(
            f"{ts_code} {start_ts.date()}~{end_ts.date()} cash={cash:.2f} "
            f"position_value={position_value:.2f} equity={equity:.2f} "
            f"profit={profit:.2f} return={return_rate:.2%}"
        )
        return profit

    def fully_regression(
        self,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        cash_per_stock: float = 100_000.0,
    ) -> float:
        symbols = self._list_stock_symbols()
        total_initial = cash_per_stock * len(symbols)
        total_profit = 0.0

        for symbol in symbols:
            try:
                profit = self.test(symbol, start_date, end_date, initial_cash=cash_per_stock)
                total_profit += profit
            except Exception as exc:
                self.logger.warning("SKIP %s reason=%s", symbol, exc)
                continue

        total_return = (total_profit / total_initial) if total_initial > 0 else 0.0
        logging.info(
            "ALL %s~%s total_profit=%.2f total_initial=%.2f return=%.2f%%",
            pd.Timestamp(start_date).date(),
            pd.Timestamp(end_date).date(),
            total_profit,
            total_initial,
            total_return * 100,
        )
        return total_return


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run regression backtest for a strategy.")
    parser.add_argument(
        "--strategy",
        type=str,
        default="third",
        choices=sorted(STRATEGY_MAP.keys()),
        help="Strategy name",
    )
    parser.add_argument("stock_code", type=str, help="Stock code without suffix, or 'all'")
    parser.add_argument("start_date", type=str, help="YYYY-MM-DD")
    parser.add_argument("end_date", type=str, help="YYYY-MM-DD")
    parser.add_argument("--cash", type=float, default=1_000_000.0, help="Initial cash")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    strategy_cls = STRATEGY_MAP[args.strategy]
    tester = RegressionTest(strategy_cls=strategy_cls, initial_cash=args.cash)
    if args.stock_code.lower() == "all":
        tester.fully_regression(args.start_date, args.end_date, cash_per_stock=args.cash)
    else:
        tester.test(args.stock_code, args.start_date, args.end_date, initial_cash=args.cash)


if __name__ == "__main__":
    main()
