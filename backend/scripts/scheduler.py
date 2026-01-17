#!/usr/bin/env python3
from __future__ import annotations

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
INDICATORS_CMD = [
    PYTHON,
    str(SCRIPTS_ROOT / "one_time/calculate_indicators.py"),
]


def run_cmd(cmd: list[str], label: str) -> None:
    start = time.perf_counter()
    print(f"[scheduler] start {label}: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    elapsed = time.perf_counter() - start
    print(f"[scheduler] done  {label}: {elapsed:.2f}s")


def run_daily_then_indicators() -> None:
    run_cmd(DAILY_CMD, "pull_daily_history")
    run_cmd(INDICATORS_CMD, "calculate_indicators")


def main() -> None:
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
    print("[scheduler] ready: daily@18:00 Asia/Shanghai -> indicators after daily")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
