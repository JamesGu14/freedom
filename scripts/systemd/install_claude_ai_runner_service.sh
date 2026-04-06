#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-freedom-ai-runner}"
SERVICE_USER="${SERVICE_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 not found, set PYTHON_BIN manually" >&2
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "PYTHON_BIN is not executable: ${PYTHON_BIN}" >&2
  exit 1
fi

RUNNER_SCRIPT="${REPO_ROOT}/scripts/ai_runner_claude.py"
if [[ ! -f "${RUNNER_SCRIPT}" ]]; then
  echo "runner script not found: ${RUNNER_SCRIPT}" >&2
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

cat >"${TMP_FILE}" <<EOF
[Unit]
Description=Freedom Claude AI Runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${REPO_ROOT}
ExecStart=${PYTHON_BIN} ${RUNNER_SCRIPT} --host 0.0.0.0 --port 18600
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true
PrivateTmp=true
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

TARGET_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "[install] writing ${TARGET_PATH}"
sudo cp "${TMP_FILE}" "${TARGET_PATH}"
sudo chmod 644 "${TARGET_PATH}"

echo "[install] reloading systemd"
sudo systemctl daemon-reload

echo "[install] enabling and starting ${SERVICE_NAME}"
sudo systemctl enable --now "${SERVICE_NAME}"

echo "[install] status"
sudo systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,40p'
