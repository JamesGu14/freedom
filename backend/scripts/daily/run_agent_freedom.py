#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.services.agent_freedom_service import run_agent_freedom_daily  # noqa: E402


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run agent_freedom daily workflow")
    parser.add_argument("--trade-date", type=str, default="", help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--strategy-version-id", type=str, default="")
    parser.add_argument("--account-id", type=str, default="main")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    result = run_agent_freedom_daily(
        trade_date=args.trade_date or None,
        strategy_version_id=args.strategy_version_id or None,
        account_id=args.account_id,
    )
    logger.info("agent_freedom finished: %s", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
