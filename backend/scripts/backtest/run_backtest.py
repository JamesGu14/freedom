#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_backtest_store import normalize_date  # noqa: E402
from app.data.mongo_backtest import ensure_strategy_backtest_indexes, get_backtest_run, get_strategy_version  # noqa: E402
from app.quant.engine import BacktestRunConfig, run_backtest_with_guard  # noqa: E402
from app.quant.params_registry import validate_and_normalize_params  # noqa: E402
from app.quant.registry import load_strategy  # noqa: E402
from app.services.backtest_service import create_backtest_run_meta  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backtest by strategy version.")
    parser.add_argument("--run-id", type=str, default="", help="Existing run_id to execute.")
    parser.add_argument("--strategy-id", type=str, default="", help="Strategy definition ID.")
    parser.add_argument("--strategy-version-id", type=str, default="", help="Strategy version ID.")
    parser.add_argument("--start-date", type=str, default="", help="Start date YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--end-date", type=str, default="", help="End date YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0, help="Initial capital.")
    parser.add_argument("--run-type", type=str, default="range", choices=["range", "full_history"], help="Run type.")
    parser.add_argument("--strategy-key", type=str, default="", help="Engine strategy key, default from params_snapshot.strategy_key or multifactor_v1.")
    parser.add_argument("--created-by", type=str, default="system", help="created_by username.")
    return parser.parse_args()


def _resolve_run_from_args(args: argparse.Namespace) -> dict[str, object]:
    ensure_strategy_backtest_indexes()
    if args.run_id:
        existing = get_backtest_run(args.run_id.strip())
        if not existing:
            raise ValueError(f"run not found: {args.run_id}")
        return existing

    if not args.strategy_id or not args.strategy_version_id:
        raise ValueError("--strategy-id and --strategy-version-id are required when --run-id is empty")
    if not args.start_date or not args.end_date:
        raise ValueError("--start-date and --end-date are required when --run-id is empty")

    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    run = create_backtest_run_meta(
        strategy_id=args.strategy_id.strip(),
        strategy_version_id=args.strategy_version_id.strip(),
        start_date=start_date,
        end_date=end_date,
        run_type=args.run_type,
        initial_capital=args.initial_capital,
        created_by=args.created_by,
    )
    return run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    run = _resolve_run_from_args(args)

    run_id = str(run.get("run_id") or "")
    strategy_id = str(run.get("strategy_id") or "")
    strategy_version_id = str(run.get("strategy_version_id") or "")
    start_date = str(run.get("start_date") or "")
    end_date = str(run.get("end_date") or "")
    initial_capital = float(run.get("initial_capital") or args.initial_capital)

    version = get_strategy_version(strategy_version_id)
    if not version:
        raise ValueError(f"strategy version not found: {strategy_version_id}")
    raw_params_snapshot = dict(version.get("params_snapshot") or {})
    version_strategy_key = str(version.get("strategy_key") or "").strip() or str(raw_params_snapshot.get("strategy_key") or "multifactor_v1")
    cli_strategy_key = args.strategy_key.strip()
    if cli_strategy_key and cli_strategy_key != version_strategy_key:
        raise ValueError(
            f"--strategy-key mismatch: cli={cli_strategy_key}, version={version_strategy_key}, strategy_version_id={strategy_version_id}"
        )
    strategy_key = cli_strategy_key or version_strategy_key
    params_snapshot, _ = validate_and_normalize_params(strategy_key, raw_params_snapshot)

    strategy = load_strategy(strategy_key)
    logger.info(
        "run_backtest start: run_id=%s strategy_id=%s strategy_version_id=%s strategy_key=%s start=%s end=%s",
        run_id,
        strategy_id,
        strategy_version_id,
        strategy_key,
        start_date,
        end_date,
    )

    config = BacktestRunConfig(
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        params_snapshot=params_snapshot,
    )
    summary = run_backtest_with_guard(strategy=strategy, config=config)
    logger.info("run_backtest done: run_id=%s summary=%s", run_id, summary)


if __name__ == "__main__":
    main()
