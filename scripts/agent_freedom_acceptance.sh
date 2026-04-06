#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <trade_date: YYYYMMDD>" >&2
  exit 1
fi

TRADE_DATE="$1"
if [[ ! "${TRADE_DATE}" =~ ^[0-9]{8}$ ]]; then
  echo "invalid trade date: ${TRADE_DATE}" >&2
  exit 1
fi

FREEDOM_USER="${FREEDOM_USER:-james}"
FREEDOM_PASSWORD="${FREEDOM_PASSWORD:-james1031}"

echo "[acceptance] 1/3 runner health from host"
python - <<'PY'
import json
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
resp = opener.open("http://127.0.0.1:18600/health", timeout=5)
payload = json.loads(resp.read().decode("utf-8"))
if not payload.get("ok"):
    raise SystemExit("runner health check failed on host")
print("[ok] host runner health:", payload)
PY

echo "[acceptance] 2/3 runner reachable from backend container"
docker compose exec -T backend python - <<'PY'
import json
import urllib.request

resp = urllib.request.urlopen("http://host.docker.internal:18600/health", timeout=5)
payload = json.loads(resp.read().decode("utf-8"))
if not payload.get("ok"):
    raise SystemExit("runner health check failed inside backend")
print("[ok] backend -> runner health:", payload)
PY

echo "[acceptance] 3/3 end-to-end run + assertions"
docker compose exec -T backend env \
  FREEDOM_USER="${FREEDOM_USER}" \
  FREEDOM_PASSWORD="${FREEDOM_PASSWORD}" \
  TRADE_DATE="${TRADE_DATE}" \
  python - <<'PY'
import json
import os
import sys
import requests

base = "http://127.0.0.1:9000/api"
trade_date = os.environ["TRADE_DATE"]
username = os.environ["FREEDOM_USER"]
password = os.environ["FREEDOM_PASSWORD"]

login = requests.post(
    f"{base}/auth/login",
    json={"username": username, "password": password},
    timeout=30,
)
login.raise_for_status()
token = login.json().get("access_token")
if not token:
    print("[fail] login missing token")
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}
run = requests.post(
    f"{base}/agent-freedom/run?trade_date={trade_date}",
    headers=headers,
    timeout=420,
)
run.raise_for_status()
run_data = run.json()
stats = run_data.get("stats") or {}
degrade_flags = run_data.get("degrade_flags") or []

report = requests.get(
    f"{base}/agent-freedom/report/latest?trade_date={trade_date}",
    headers=headers,
    timeout=30,
)
report.raise_for_status()
report_item = (report.json().get("item") or {})

calls = requests.get(
    f"{base}/agent-freedom/skill-calls?trade_date={trade_date}&page_size=20",
    headers=headers,
    timeout=30,
)
calls.raise_for_status()
call_items = calls.json().get("items") or []

errors = []
if stats.get("skill_success_rate") != 1.0:
    errors.append(f"skill_success_rate != 1.0, got {stats.get('skill_success_rate')}")
if int(stats.get("skill_degrade_count") or 0) != 0:
    errors.append(f"skill_degrade_count != 0, got {stats.get('skill_degrade_count')}")
if str(stats.get("signal_generate_status") or "") != "success":
    errors.append(f"signal_generate_status != success, got {stats.get('signal_generate_status')}")
if int(stats.get("signal_base_upserted") or 0) <= 0:
    errors.append(f"signal_base_upserted <= 0, got {stats.get('signal_base_upserted')}")
if int(stats.get("signal_updated") or 0) <= 0:
    errors.append(f"signal_updated <= 0, got {stats.get('signal_updated')}")
allowed_flags = {"data_quality:degraded"}
if any(flag not in allowed_flags for flag in degrade_flags):
    errors.append(f"unexpected degrade_flags: {degrade_flags}")

summary = {
    "run_status": run_data.get("status"),
    "degrade_flags": degrade_flags,
    "stats": stats,
    "report_status": report_item.get("status"),
    "skill_calls_sample": [
        {
            "skill_name": item.get("skill_name"),
            "status": item.get("status"),
            "ok": item.get("ok"),
        }
        for item in call_items[:3]
    ],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

if errors:
    print("[acceptance] FAILED")
    for err in errors:
        print(" -", err)
    sys.exit(1)

print("[acceptance] PASSED")
PY
