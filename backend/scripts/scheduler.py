#!/usr/bin/env python3
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

SCRIPTS_ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

DAILY_CMD = [
    PYTHON,
    str(SCRIPTS_ROOT / "daily/pull_daily_history.py"),
    "--last-days",
    "1",
]
STK_FACTOR_CMD = [
    PYTHON,
    str(SCRIPTS_ROOT / "daily/sync_stk_factor_pro.py"),
    "--last-days",
    "1",
]

logger = logging.getLogger(__name__)


def run_cmd(cmd: list[str], label: str) -> None:
    start = time.perf_counter()
    logger.info("[scheduler] start %s: %s", label, " ".join(cmd))
    subprocess.run(cmd, check=True)
    elapsed = time.perf_counter() - start
    logger.info("[scheduler] done  %s: %.2fs", label, elapsed)


def run_daily_then_indicators() -> None:
    run_cmd(DAILY_CMD, "pull_daily_history")
    run_cmd(STK_FACTOR_CMD, "sync_stk_factor_pro")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    tz = ZoneInfo("Asia/Shanghai")
    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        run_daily_then_indicators,
        CronTrigger(hour=18, minute=0, timezone=tz),
        id="job_daily_then_indicators",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    logger.info("[scheduler] ready: daily@18:00 Asia/Shanghai -> stk_factor_pro after daily")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
