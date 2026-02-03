#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/james/projects/freedom"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"

TODAY="$(date +%Y%m%d)"
LOG_FILE="${LOG_DIR}/daily_${TODAY}.log"

cd "${ROOT_DIR}"

# Activate conda environment
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate freedom

echo "[INFO] $(date '+%F %T') start daily tasks for ${TODAY}" | tee -a "${LOG_FILE}"

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
run_task "拉取每日个股日线" "python backend/scripts/daily/pull_daily_history.py --last-days 1"

# 2) Calculate indicators
run_task "计算每日指标" "python backend/scripts/one_time/calculate_indicators.py"

# 3) Calculate daily signals
run_task "计算每日信号" "cd /home/james/projects/freedom/backend && python -m scripts.daily.calculate_signal --start-date 20260126"

# 4) Sync Shenwan industry members (incremental)
# run_task "sync_shenwan_members" "python backend/scripts/daily/sync_shenwan_members.py --incremental"

# 5) Sync Shenwan daily index (last 1 trading day)
run_task "同步申万行业日线" "python backend/scripts/daily/sync_shenwan_daily.py --last-days 1"

# Optional compaction (enable if needed)
# python backend/scripts/daily/compact_daily_parquet.py | tee -a "${LOG_FILE}"
# python backend/scripts/daily/compact_daily_basic_parquet.py | tee -a "${LOG_FILE}"

echo "[INFO] $(date '+%F %T') done" | tee -a "${LOG_FILE}"
