#!/bin/bash
# 补齐财务数据历史脚本 (2020-2024)
# 使用方法: ./scripts/backfill_financial_history.sh

set -e

ROOT_DIR="/home/james/projects/freedom"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"

cd "${ROOT_DIR}"
export PYTHONPATH="${ROOT_DIR}/backend"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate freedom

echo "=== 开始补齐财务数据历史 (2020-2024) ==="
echo "日志目录: ${LOG_DIR}"

# 1. forecast (业绩预告)
echo ""
echo "[1/5] 同步 forecast 历史数据..."
nohup python backend/scripts/daily/sync_financial_reports.py \
    --dataset forecast \
    --start-date 20200101 \
    --end-date 20241231 \
    > "${LOG_DIR}/sync_forecast_history.log" 2>&1 &
FORECAST_PID=$!
echo "  - forecast PID: $FORECAST_PID"

# 2. express (业绩快报)
echo ""
echo "[2/5] 同步 express 历史数据..."
nohup python backend/scripts/daily/sync_financial_reports.py \
    --dataset express \
    --start-date 20200101 \
    --end-date 20241231 \
    > "${LOG_DIR}/sync_express_history.log" 2>&1 &
EXPRESS_PID=$!
echo "  - express PID: $EXPRESS_PID"

# 3. disclosure_date (财报披露日期)
echo ""
echo "[3/5] 同步 disclosure_date 历史数据..."
(
    for year in 2020 2021 2022 2023 2024; do
        echo "=== 同步 ${year} 年 ==="
        python backend/scripts/daily/sync_disclosure_date.py --year $year
    done
) > "${LOG_DIR}/sync_disclosure_date_history.log" 2>&1 &
DISCLOSURE_PID=$!
echo "  - disclosure_date PID: $DISCLOSURE_PID"

# 4. fina_audit (财务审计意见) - 遍历股票较慢
echo ""
echo "[4/5] 同步 fina_audit 历史数据 (约1.5小时)..."
nohup python backend/scripts/daily/sync_fina_audit.py \
    --last-days 2000 \
    > "${LOG_DIR}/sync_fina_audit_history.log" 2>&1 &
AUDIT_PID=$!
echo "  - fina_audit PID: $AUDIT_PID"

# 5. fina_mainbz (主营业务构成) - 最慢，每季度运行
echo ""
echo "[5/5] 同步 fina_mainbz 历史数据 (约2-3小时)..."
nohup python backend/scripts/daily/sync_fina_mainbz.py \
    --period-start 20200101 \
    --period-end 20241231 \
    > "${LOG_DIR}/sync_fina_mainbz_history.log" 2>&1 &
MAINBZ_PID=$!
echo "  - fina_mainbz PID: $MAINBZ_PID"

echo ""
echo "=== 所有同步任务已启动 ==="
echo ""
echo "进程ID:"
echo "  forecast:       $FORECAST_PID"
echo "  express:        $EXPRESS_PID"
echo "  disclosure:     $DISCLOSURE_PID"
echo "  fina_audit:     $AUDIT_PID"
echo "  fina_mainbz:    $MAINBZ_PID"
echo ""
echo "查看日志:"
echo "  tail -f ${LOG_DIR}/sync_forecast_history.log"
echo "  tail -f ${LOG_DIR}/sync_express_history.log"
echo "  tail -f ${LOG_DIR}/sync_disclosure_date_history.log"
echo "  tail -f ${LOG_DIR}/sync_fina_audit_history.log"
echo "  tail -f ${LOG_DIR}/sync_fina_mainbz_history.log"
echo ""
echo "查看进度:"
echo "  ps aux | grep sync_ | grep -v grep"
