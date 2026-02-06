#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/james/projects/freedom"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"

# Parse command line arguments
START_DATE=""
END_DATE=""

usage() {
    echo "Usage: $0 [--start-date YYYYMMDD] [--end-date YYYYMMDD]"
    echo ""
    echo "Options:"
    echo "  --start-date    Start date in YYYYMMDD or YYYY-MM-DD format"
    echo "  --end-date      End date in YYYYMMDD or YYYY-MM-DD format (default: today)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run for today only"
    echo "  $0 --start-date 20250101              # Run from 2025-01-01 to today"
    echo "  $0 --start-date 20250101 --end-date 20250131   # Run for specific range"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --start-date)
            START_DATE="$2"
            shift 2
            ;;
        --end-date)
            END_DATE="$2"
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
    # No dates specified, use today
    START_DATE="$(date +%Y%m%d)"
    END_DATE="${START_DATE}"
    echo "[INFO] No date range specified, running for today: ${START_DATE}"
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

run_task() {
  local task_name="$1"
  local command="$2"
  echo "[INFO] $(date '+%F %T') start ${task_name}" | tee -a "${LOG_FILE}"
  eval "${command}" | tee -a "${LOG_FILE}"
  echo "[INFO] $(date '+%F %T') end ${task_name}" | tee -a "${LOG_FILE}"
}

# Check trade calendar (SSE). Skip if not trading day.
echo "[INFO] $(date '+%F %T') start check_trade_calendar" | tee -a "${LOG_FILE}"
IS_OPEN="$(python - <<'PY'
import datetime as dt
from app.data.mongo_trade_calendar import is_trading_day

today = dt.datetime.now().strftime("%Y%m%d")
print("1" if is_trading_day(today, exchange="SSE") else "0")
PY
)"
echo "[INFO] $(date '+%F %T') end check_trade_calendar" | tee -a "${LOG_FILE}"

if [[ "${IS_OPEN}" != "1" ]]; then
  echo "[INFO] ${TODAY} is not a trading day, skip." | tee -a "${LOG_FILE}"
  exit 0
fi

echo "[INFO] ${TODAY} is trading day, running tasks..." | tee -a "${LOG_FILE}"

# 1) Pull daily market data (K-line)
run_task "拉取每日个股日线" "python backend/scripts/daily/pull_daily_history.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 2) Calculate indicators for the date range
run_task "计算每日指标" "python backend/scripts/one_time/calculate_indicators.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 3) Calculate daily signals for the date range
run_task "计算每日信号" "cd /home/james/projects/freedom/backend && python -m scripts.daily.calculate_signal --start-date ${START_DATE} --end-date ${END_DATE}"

# 4) Sync Shenwan industry members (incremental)
# run_task "sync_shenwan_members" "python backend/scripts/daily/sync_shenwan_members.py --incremental"

# 5) Sync Shenwan daily index for the date range
run_task "同步申万行业日线" "python backend/scripts/daily/sync_shenwan_daily.py --start-date ${START_DATE} --end-date ${END_DATE}"

# Optional compaction (enable if needed)
# python backend/scripts/daily/compact_daily_parquet.py | tee -a "${LOG_FILE}"
# python backend/scripts/daily/compact_daily_basic_parquet.py | tee -a "${LOG_FILE}"

echo "[INFO] $(date '+%F %T') done" | tee -a "${LOG_FILE}"
