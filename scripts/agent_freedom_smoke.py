#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from urllib import parse, request


def _post_json(url: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, token: str | None = None) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for agent_freedom APIs")
    parser.add_argument("--base-url", type=str, default="http://localhost:9000/api")
    parser.add_argument("--username", type=str, default="james")
    parser.add_argument("--password", type=str, default="james1031")
    parser.add_argument("--trade-date", type=str, required=True, help="YYYYMMDD")
    parser.add_argument("--account-id", type=str, default="main")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    login = _post_json(
        f"{base}/auth/login",
        {
            "username": args.username,
            "password": args.password,
        },
    )
    token = str(login.get("access_token") or "").strip()
    if not token:
        print("[smoke] login failed: missing token", file=sys.stderr)
        sys.exit(1)

    run_query = parse.urlencode({"trade_date": args.trade_date, "account_id": args.account_id})
    run_result = _post_json(f"{base}/agent-freedom/run?{run_query}", payload={}, token=token)

    report_query = parse.urlencode({"trade_date": args.trade_date})
    report_result = _get_json(f"{base}/agent-freedom/report/latest?{report_query}", token=token)
    calls_result = _get_json(f"{base}/agent-freedom/skill-calls?{report_query}", token=token)

    output = {
        "run": run_result,
        "report": report_result,
        "skill_calls": {
            "total": calls_result.get("total"),
            "sample": (calls_result.get("items") or [])[:3],
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
