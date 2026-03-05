#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/james/projects/freedom"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"

# Parse command line arguments
START_DATE=""
END_DATE=""
HAS_DATE_ARGS="0"

usage() {
    echo "Usage: $0 [--start-date YYYYMMDD] [--end-date YYYYMMDD]"
    echo ""
    echo "Options:"
    echo "  --start-date    Start date in YYYYMMDD or YYYY-MM-DD format"
    echo "  --end-date      End date in YYYYMMDD or YYYY-MM-DD format (default: today)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run for latest open trading day"
    echo "  $0 --start-date 20250101              # Run from 2025-01-01 to today"
    echo "  $0 --start-date 20250101 --end-date 20250131   # Run for specific range"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --start-date)
            START_DATE="$2"
            HAS_DATE_ARGS="1"
            shift 2
            ;;
        --end-date)
            END_DATE="$2"
            HAS_DATE_ARGS="1"
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Set default values
if [[ -z "${START_DATE}" && -z "${END_DATE}" ]]; then
    # No dates specified: use latest open trading day to avoid "early morning skip today"
    LATEST_OPEN_DATE="$(
      PYTHONPATH="${ROOT_DIR}/backend" python - <<'PY'
import datetime as dt
from app.data.mongo import get_collection

today = dt.datetime.now().strftime("%Y%m%d")
doc = get_collection("trade_calendar").find_one(
    {"exchange": "SSE", "cal_date": {"$lte": today}, "is_open": {"$in": ["1", 1]}},
    {"_id": 0, "cal_date": 1},
    sort=[("cal_date", -1)],
)
print(doc.get("cal_date") if doc else today)
PY
)"
    START_DATE="${LATEST_OPEN_DATE}"
    END_DATE="${LATEST_OPEN_DATE}"
    echo "[INFO] No date range specified, running for latest open trading day: ${START_DATE}"
elif [[ -z "${END_DATE}" ]]; then
    # Only start date specified, use today as end date
    END_DATE="$(date +%Y%m%d)"
    echo "[INFO] Running from ${START_DATE} to ${END_DATE}"
else
    echo "[INFO] Running from ${START_DATE} to ${END_DATE}"
fi

TODAY="$(date +%Y%m%d)"
LOG_FILE="${LOG_DIR}/daily_${TODAY}_${START_DATE}_${END_DATE}.log"

cd "${ROOT_DIR}"

# Activate conda environment
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate freedom

echo "[INFO] $(date '+%F %T') start daily tasks for ${START_DATE} to ${END_DATE}" | tee -a "${LOG_FILE}"

TOTAL_STEPS=7

run_step_task() {
  local step_no="$1"
  local task_name="$2"
  local command="$3"
  echo "[INFO] $(date '+%F %T') [Step ${step_no}/${TOTAL_STEPS}] start ${task_name}" | tee -a "${LOG_FILE}"
  eval "${command}" | tee -a "${LOG_FILE}"
  echo "[INFO] $(date '+%F %T') [Step ${step_no}/${TOTAL_STEPS}] end ${task_name}" | tee -a "${LOG_FILE}"
}

skip_step() {
  local step_no="$1"
  local task_name="$2"
  local reason="$3"
  echo "[INFO] $(date '+%F %T') [Step ${step_no}/${TOTAL_STEPS}] skip ${task_name}: ${reason}" | tee -a "${LOG_FILE}"
}

# 当用户未显式指定日期时（默认“最近交易日”模式），若目标日期非交易日则直接跳过。
# 当用户显式传入日期区间时，不在此处提前退出，由各任务按交易日自行处理。
if [[ "${HAS_DATE_ARGS}" == "0" ]]; then
  echo "[INFO] $(date '+%F %T') start check_trade_calendar" | tee -a "${LOG_FILE}"
# Bug fix: check TODAY's date, not END_DATE (which is always a trading day)
TODAY_DATE="$(date +%Y%m%d)"
IS_OPEN="$(
CHECK_DATE="${TODAY_DATE}" PYTHONPATH="${ROOT_DIR}/backend" python - <<'PY'
import sys
from app.data.mongo_trade_calendar import is_trading_day

import os
check_date = os.environ.get("CHECK_DATE", "")
sys.stdout.write("1" if is_trading_day(check_date, exchange="SSE") else "0")
PY
)"
  echo "[INFO] $(date '+%F %T') end check_trade_calendar" | tee -a "${LOG_FILE}"

  if [[ "${IS_OPEN}" != "1" ]]; then
    echo "[INFO] ${TODAY_DATE} is not a trading day, skip." | tee -a "${LOG_FILE}"
    exit 0
  fi

  echo "[INFO] ${TODAY_DATE} is trading day, running tasks..." | tee -a "${LOG_FILE}"
else
  echo "[INFO] date range provided, skip global today-trading-day guard" | tee -a "${LOG_FILE}"
fi

# 1) Pull daily market data (K-line)
run_step_task "1" "拉取每日个股日线" "python backend/scripts/daily/pull_daily_history.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 2) Sync technical factors for the date range
run_step_task "2" "同步每日技术因子" "python backend/scripts/daily/sync_stk_factor_pro.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 3) Calculate daily signals for the date range
skip_step "3" "计算每日信号" "暂时注释禁用"
# run_step_task "3" "计算每日信号" "cd /home/james/projects/freedom/backend && python -m scripts.daily.calculate_signal --start-date ${START_DATE} --end-date ${END_DATE}"

# 4) Sync Shenwan industry members (incremental)
# Bug fix: when no date args, use today's calendar weekday (not END_DATE's weekday,
# which is always a trading day and causes weekly tasks to re-run on weekends).
if [[ "${HAS_DATE_ARGS}" == "0" ]]; then
  TARGET_WEEKDAY="$(python3 -c "import datetime; print(datetime.datetime.now().isoweekday())")"
else
  TARGET_WEEKDAY="$(
END_DATE="${END_DATE}" PYTHONPATH="${ROOT_DIR}/backend" python - <<'PY'
import datetime as dt
import os
text = str(os.environ.get("END_DATE", "")).replace("-", "")
print(dt.datetime.strptime(text, "%Y%m%d").isoweekday())
PY
)"
fi
if [[ "${TARGET_WEEKDAY}" == "5" ]]; then
  run_step_task "4" "同步申万行业成分(每周五)" "python backend/scripts/daily/sync_shenwan_members.py --incremental --sync-date ${END_DATE}"
else
  skip_step "4" "同步申万行业成分(每周五)" "非周五"
fi

# 5) Sync Shenwan daily index for the date range
run_step_task "5" "同步申万行业日线" "python backend/scripts/daily/sync_shenwan_daily.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 6) Sync index-related data (CITIC daily, market dailybasic, index factors)
run_step_task "6" "同步指数数据(中信/大盘/申万因子)" "python backend/scripts/daily/sync_zhishu_data.py --start-date ${START_DATE} --end-date ${END_DATE} --modules all --skip-members"

# 7) Compact fragmented parquet files (weekly to reduce daily runtime)
if [[ "${TARGET_WEEKDAY}" == "5" ]]; then
  run_step_task "7" "压缩Parquet文件(每周五)" "python backend/scripts/daily/compact_parquet.py --dataset all --sync-date ${END_DATE}"
else
  skip_step "7" "压缩Parquet文件(每周五)" "非周五"
fi

echo "[INFO] $(date '+%F %T') done" | tee -a "${LOG_FILE}"
