#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FREEDOM_ROOT_DIR:-/home/james/projects/freedom}"
PROJECT_LOG_DIR="${ROOT_DIR}/logs/airflow_jobs"
BACKEND_ENV_FILE="${ROOT_DIR}/backend/.env"

DAG_ID=""
TASK_ID=""
RUN_ID=""
TRADE_DATE=""

usage() {
    echo "Usage: $0 --dag-id <dag_id> --task-id <task_id> --run-id <run_id> --trade-date <trade_date> -- <command...>"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dag-id)
            DAG_ID="$2"
            shift 2
            ;;
        --task-id)
            TASK_ID="$2"
            shift 2
            ;;
        --run-id)
            RUN_ID="$2"
            shift 2
            ;;
        --trade-date)
            TRADE_DATE="$2"
            shift 2
            ;;
        --)
            shift
            break
            ;;
        *)
            usage
            ;;
    esac
done

if [[ -z "${DAG_ID}" || -z "${TASK_ID}" || -z "${RUN_ID}" || -z "${TRADE_DATE}" || $# -eq 0 ]]; then
    usage
fi

LOG_DIR="${PROJECT_LOG_DIR}/${DAG_ID}/${RUN_ID}"
LOG_FILE="${LOG_DIR}/${TASK_ID}.log"
mkdir -p "${LOG_DIR}"

if [[ -f "${BACKEND_ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${BACKEND_ENV_FILE}"
    set +a
fi

if [[ -z "${TUSHARE_TOKEN:-}" ]] && command -v zsh >/dev/null 2>&1; then
    TUSHARE_TOKEN_FROM_ZSH="$(zsh -ic 'print -r -- ${TUSHARE_TOKEN:-}' 2>/dev/null | tail -n 1)"
    if [[ -n "${TUSHARE_TOKEN_FROM_ZSH}" ]]; then
        export TUSHARE_TOKEN="${TUSHARE_TOKEN_FROM_ZSH}"
    fi
fi

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
else
    echo "[ERROR] conda init script not found" | tee -a "${LOG_FILE}"
    exit 127
fi
conda activate freedom

export PYTHONPATH="${ROOT_DIR}/backend${PYTHONPATH:+:${PYTHONPATH}}"
cd "${ROOT_DIR}"

echo "[INFO] $(date '+%F %T') dag_id=${DAG_ID} task_id=${TASK_ID} run_id=${RUN_ID} trade_date=${TRADE_DATE}" | tee -a "${LOG_FILE}"
echo "[INFO] $(date '+%F %T') command=$*" | tee -a "${LOG_FILE}"
"$@" 2>&1 | tee -a "${LOG_FILE}"
echo "[INFO] $(date '+%F %T') done task_id=${TASK_ID}" | tee -a "${LOG_FILE}"
