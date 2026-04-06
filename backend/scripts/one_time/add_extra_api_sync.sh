#!/usr/bin/env bash
# 一次性全量历史数据同步脚本：add-extra-api 新增数据源
# 对应 openspec/changes/add-extra-api 需求
#
# 使用方法：
#   bash backend/scripts/one_time/add_extra_api_sync.sh [--skip-step N,M,...]
#
# 各步骤说明：
#   Step 1  cyq_perf        筹码胜率（2018-01-01 起）        ~Parquet
#   Step 2  moneyflow_dc    东方财富个股资金流（2023-09-11 起）~Parquet
#   Step 3  idx_factor_pro  指数技术因子（2015-01-01 起）     ~Parquet
#   Step 4  moneyflow_hsgt  沪深港通资金流（2015-01-01 起）   ~MongoDB
#   Step 5  ccass_hold      CCASS中央结算持股（2015-01-01 起）~MongoDB
#   Step 6  hk_hold         港股通持股明细（2015-01-01 起）   ~MongoDB
#   Step 7  stk_surv        机构调研记录（2015-01-01 起）     ~MongoDB
#   Step 8  cyq_chips       筹码分布（2018-01-01 起）        ~Parquet（数据量大，15-35 GB）
#
# 注意：
#   - 所有脚本的 END_DATE 设为 20261231，确保拉满至今
#   - 建议在网络稳定、TuShare 积分充足时夜间运行

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"

TODAY="$(date +%Y%m%d)"
LOG_FILE="${LOG_DIR}/add_extra_api_sync_${TODAY}.log"

cd "${ROOT_DIR}"

# 解析 --skip-step 参数
SKIP_STEPS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-step)
            SKIP_STEPS="$2"
            shift 2
            ;;
        --help|-h)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

should_skip() {
    local step="$1"
    if [[ -z "${SKIP_STEPS}" ]]; then
        return 1
    fi
    IFS=',' read -ra skips <<< "${SKIP_STEPS}"
    for s in "${skips[@]}"; do
        if [[ "$s" == "$step" ]]; then
            return 0
        fi
    done
    return 1
}

# 激活 conda 环境
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate freedom

TOTAL_STEPS=8

run_step() {
    local step_no="$1"
    local task_name="$2"
    local command="$3"

    if should_skip "${step_no}"; then
        echo "[INFO] $(date '+%F %T') [Step ${step_no}/${TOTAL_STEPS}] SKIP ${task_name} (--skip-step)" | tee -a "${LOG_FILE}"
        return 0
    fi

    echo "" | tee -a "${LOG_FILE}"
    echo "[INFO] $(date '+%F %T') [Step ${step_no}/${TOTAL_STEPS}] START ${task_name}" | tee -a "${LOG_FILE}"
    eval "${command}" 2>&1 | tee -a "${LOG_FILE}"
    echo "[INFO] $(date '+%F %T') [Step ${step_no}/${TOTAL_STEPS}] END   ${task_name}" | tee -a "${LOG_FILE}"
}

echo "========================================================" | tee -a "${LOG_FILE}"
echo "[INFO] $(date '+%F %T') add-extra-api 全量历史同步开始" | tee -a "${LOG_FILE}"
echo "[INFO] 日志文件: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "========================================================" | tee -a "${LOG_FILE}"

# Step 1: 筹码胜率 cyq_perf（2018-01-01 起）
run_step "1" "筹码胜率 cyq_perf" \
    "python backend/scripts/daily/sync_cyq_perf.py --start-date 20180101 --end-date 20261231 --sleep 0.1"

# Step 2: 东方财富个股资金流 moneyflow_dc（2023-09-11 起）
run_step "2" "东方财富个股资金流 moneyflow_dc" \
    "python backend/scripts/daily/sync_moneyflow_dc.py --start-date 20230911 --end-date 20261231 --sleep 0.1"

# Step 3: 指数技术因子 idx_factor_pro（2015-01-01 起）
run_step "3" "指数技术因子 idx_factor_pro" \
    "python backend/scripts/daily/sync_idx_factor_pro.py --start-date 20150101 --end-date 20261231 --sleep 0.1"

# Step 4: 沪深港通资金流 moneyflow_hsgt（2015-01-01 起）
run_step "4" "沪深港通资金流 moneyflow_hsgt" \
    "python backend/scripts/daily/sync_moneyflow_hsgt.py --start-date 20150101 --end-date 20261231"

# Step 5: CCASS 中央结算持股 ccass_hold（2015-01-01 起）
run_step "5" "CCASS中央结算持股 ccass_hold" \
    "python backend/scripts/daily/sync_ccass_hold.py --start-date 20150101 --end-date 20261231 --sleep 0.1"

# Step 6: 港股通持股明细 hk_hold（2015-01-01 起）
run_step "6" "港股通持股明细 hk_hold" \
    "python backend/scripts/daily/sync_hk_hold.py --start-date 20150101 --end-date 20261231 --sleep 0.1"

# Step 7: 机构调研记录 stk_surv（2015-01-01 起）
run_step "7" "机构调研记录 stk_surv" \
    "python backend/scripts/daily/sync_stk_surv.py --start-date 20150101 --end-date 20261231 --sleep 0.1"

# Step 8: 筹码分布 cyq_chips（2018-01-01 起，数据量大，保守用 0.3）
run_step "8" "筹码分布 cyq_chips（数据量大，预计耗时较长）" \
    "python backend/scripts/daily/sync_cyq_chips.py --start-date 20180101 --end-date 20261231 --sleep 0.3"

echo "" | tee -a "${LOG_FILE}"
echo "========================================================" | tee -a "${LOG_FILE}"
echo "[INFO] $(date '+%F %T') 全量历史同步完成 ✓" | tee -a "${LOG_FILE}"
echo "========================================================" | tee -a "${LOG_FILE}"
