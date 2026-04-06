#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/james/projects/freedom"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PROJECT_ROOT="$TMP_DIR/freedom"
mkdir -p "$PROJECT_ROOT/scripts" "$PROJECT_ROOT/backend"
cp "$ROOT/scripts/run_freedom_sync_job.sh" "$PROJECT_ROOT/scripts/run_freedom_sync_job.sh"
chmod +x "$PROJECT_ROOT/scripts/run_freedom_sync_job.sh"

cat >"$PROJECT_ROOT/backend/.env" <<'EOF'
TUSHARE_TOKEN=test-token
CUSTOM_FLAG=from-env
EOF

mkdir -p "$TMP_DIR/home/miniconda3/etc/profile.d" "$TMP_DIR/bin"
cat >"$TMP_DIR/home/miniconda3/etc/profile.d/conda.sh" <<'EOF'
conda() {
  if [[ "$1" == "activate" ]]; then
    return 0
  fi
  return 0
}
EOF

cat >"$TMP_DIR/bin/python" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "${TUSHARE_TOKEN:-missing}" > "$OUTPUT_FILE"
printf '%s\n' "${CUSTOM_FLAG:-missing}" >> "$OUTPUT_FILE"
EOF
chmod +x "$TMP_DIR/bin/python"

OUTPUT_FILE="$TMP_DIR/output.txt"
HOME="$TMP_DIR/home" PATH="$TMP_DIR/bin:$PATH" OUTPUT_FILE="$OUTPUT_FILE" \
  FREEDOM_ROOT_DIR="$PROJECT_ROOT" \
  "$PROJECT_ROOT/scripts/run_freedom_sync_job.sh" \
  --dag-id freedom_market_data_daily \
  --task-id smoke \
  --run-id test \
  --trade-date 20260302 \
  -- python -c 'print("ok")'

mapfile -t lines <"$OUTPUT_FILE"
[[ "${lines[0]}" == "test-token" ]]
[[ "${lines[1]}" == "from-env" ]]

PROJECT_ROOT_2="$TMP_DIR/freedom-zsh"
mkdir -p "$PROJECT_ROOT_2/scripts"
cp "$ROOT/scripts/run_freedom_sync_job.sh" "$PROJECT_ROOT_2/scripts/run_freedom_sync_job.sh"
chmod +x "$PROJECT_ROOT_2/scripts/run_freedom_sync_job.sh"

cat >"$TMP_DIR/bin/zsh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "zsh-token"
EOF
chmod +x "$TMP_DIR/bin/zsh"

HOME="$TMP_DIR/home" PATH="$TMP_DIR/bin:$PATH" OUTPUT_FILE="$OUTPUT_FILE" \
  FREEDOM_ROOT_DIR="$PROJECT_ROOT_2" \
  "$PROJECT_ROOT_2/scripts/run_freedom_sync_job.sh" \
  --dag-id freedom_market_data_daily \
  --task-id smoke \
  --run-id test-zsh \
  --trade-date 20260302 \
  -- python -c 'print("ok")'

mapfile -t lines <"$OUTPUT_FILE"
[[ "${lines[0]}" == "zsh-token" ]]
