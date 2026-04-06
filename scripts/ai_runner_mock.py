#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except Exception:
        length = 0
    raw = handler.rfile.read(max(length, 0)) if length > 0 else b"{}"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _normalize_ts_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text


def _build_findata_payload(input_data: dict[str, Any]) -> dict[str, Any]:
    market = input_data.get("market") if isinstance(input_data.get("market"), dict) else {}
    pct_change = 0.0
    try:
        pct_change = float(market.get("pct_change") or 0.0)
    except Exception:
        pct_change = 0.0

    macro_score = 50.0 + max(min(pct_change * 5.0, 20.0), -20.0)
    northbound_score = 50.0 + max(min(pct_change * 4.0, 20.0), -20.0)

    if macro_score >= 60 and northbound_score >= 60:
        hint = "risk_on"
    elif macro_score <= 40 and northbound_score <= 40:
        hint = "risk_off"
    else:
        hint = "neutral"

    return {
        "macro_score": round(macro_score, 4),
        "northbound_score": round(northbound_score, 4),
        "risk_hint": hint,
    }


def _build_quant_factor_payload(input_data: dict[str, Any]) -> dict[str, Any]:
    stocks = input_data.get("stocks") if isinstance(input_data.get("stocks"), list) else []
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(stocks[:300]):
        if not isinstance(item, dict):
            continue
        ts_code = _normalize_ts_code(item.get("ts_code"))
        if not ts_code:
            continue
        try:
            base_score = float(item.get("score") or 50.0)
        except Exception:
            base_score = 50.0
        jitter = ((idx % 7) - 3) * 0.7
        total_score = max(min(base_score + jitter, 100.0), 0.0)
        rows.append({"ts_code": ts_code, "total_score": round(total_score, 4)})

    if not rows:
        for idx in range(20):
            code = f"{idx+1:06d}.SZ"
            rows.append({"ts_code": code, "total_score": round(50 + random.uniform(-10, 10), 4)})

    return {"rows": rows}


def _build_sector_rotation_payload(input_data: dict[str, Any]) -> dict[str, Any]:
    industries = input_data.get("industries") if isinstance(input_data.get("industries"), list) else []
    rows: list[dict[str, Any]] = []
    for item in industries[:80]:
        if not isinstance(item, dict):
            continue
        code = _normalize_ts_code(item.get("industry_code"))
        if not code:
            continue

        rank = item.get("rank")
        rank_total = item.get("rank_total")
        pct_change = item.get("pct_change")

        try:
            rank_value = float(rank)
            total_value = float(rank_total)
            rank_score = 50.0 if total_value <= 1 else (1.0 - (rank_value - 1.0) / (total_value - 1.0)) * 100.0
        except Exception:
            rank_score = 50.0

        try:
            pct_value = float(pct_change)
            pct_score = max(min((pct_value + 5.0) / 10.0, 1.0), 0.0) * 100.0
        except Exception:
            pct_score = 50.0

        score = rank_score * 0.7 + pct_score * 0.3
        if score >= 70:
            bias = "overweight"
        elif score <= 35:
            bias = "underweight"
        else:
            bias = "neutral"

        rows.append(
            {
                "industry_code": code,
                "score": round(score, 4),
                "bias": bias,
            }
        )

    if not rows:
        demo = [
            ("801010.SI", 76.0, "overweight"),
            ("801080.SI", 66.0, "neutral"),
            ("801180.SI", 31.0, "underweight"),
        ]
        rows = [{"industry_code": c, "score": s, "bias": b} for c, s, b in demo]

    return {"rows": rows}


class AIRunnerMockHandler(BaseHTTPRequestHandler):
    token: str = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/", "/health"}:
            _json_response(self, {"ok": True, "service": "ai-runner-mock"})
            return
        _json_response(self, {"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.token:
            auth_header = str(self.headers.get("Authorization") or "")
            expected = f"Bearer {self.token}"
            if auth_header != expected:
                _json_response(
                    self,
                    {
                        "ok": False,
                        "status": "auth_error",
                        "error": "invalid bearer token",
                        "data": None,
                    },
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return

        if not self.path.startswith("/v1/skills/"):
            _json_response(
                self,
                {
                    "ok": False,
                    "status": "upstream_error",
                    "error": "unknown endpoint",
                    "data": None,
                },
                status=HTTPStatus.NOT_FOUND,
            )
            return

        skill_name = self.path.split("/v1/skills/", 1)[-1].strip("/")
        payload = _read_json(self)
        request_id = str(payload.get("request_id") or "")
        input_data = payload.get("input") if isinstance(payload.get("input"), dict) else {}

        if skill_name == "findata-toolkit-cn":
            data = _build_findata_payload(input_data)
        elif skill_name == "quant-factor-screener":
            data = _build_quant_factor_payload(input_data)
        elif skill_name == "sector-rotation-detector":
            data = _build_sector_rotation_payload(input_data)
        else:
            _json_response(
                self,
                {
                    "ok": False,
                    "status": "invalid_json",
                    "error": f"unsupported skill: {skill_name}",
                    "data": None,
                    "request_id": request_id,
                    "latency_ms": 1,
                    "model": "mock-v1",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        _json_response(
            self,
            {
                "ok": True,
                "status": "success",
                "error": "",
                "request_id": request_id,
                "data": data,
                "latency_ms": 5,
                "model": "mock-v1",
            },
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        # Keep terminal output concise.
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock AI Runner service for Freedom integration testing")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18600)
    parser.add_argument("--token", type=str, default="")
    args = parser.parse_args()

    AIRunnerMockHandler.token = str(args.token or "").strip()
    server = ThreadingHTTPServer((args.host, args.port), AIRunnerMockHandler)
    print(f"[ai-runner-mock] listening on http://{args.host}:{args.port}")
    print("[ai-runner-mock] endpoints: /health and /v1/skills/{findata-toolkit-cn|quant-factor-screener|sector-rotation-detector}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
