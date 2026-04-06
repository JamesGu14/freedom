#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class ClaudeRunnerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(min(value, hi), lo)


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except Exception:
        return default


def _to_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _extract_model_name(payload: dict[str, Any]) -> str:
    usage = payload.get("modelUsage")
    if isinstance(usage, dict) and usage:
        return str(next(iter(usage.keys())))
    return ""


def _call_claude(
    *,
    claude_bin: str,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    timeout_seconds: int,
) -> tuple[dict[str, Any], int, str]:
    cmd = [
        claude_bin,
        "-p",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False),
        "--permission-mode",
        "bypassPermissions",
        "--tools",
        "",
        "--no-session-persistence",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(timeout_seconds, 1),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeRunnerError("timeout", f"claude timeout: {exc}") from exc
    except FileNotFoundError as exc:
        raise ClaudeRunnerError("upstream_error", f"claude not found: {exc}") from exc
    except Exception as exc:
        raise ClaudeRunnerError("upstream_error", str(exc)) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        message = stderr or stdout or f"claude return code {completed.returncode}"
        raise ClaudeRunnerError("model_error", message)

    try:
        payload = json.loads(stdout)
    except Exception as exc:
        raise ClaudeRunnerError("invalid_json", f"claude output is not json: {exc}") from exc

    if not isinstance(payload, dict):
        raise ClaudeRunnerError("invalid_json", "claude output root is not object")
    if bool(payload.get("is_error")):
        raise ClaudeRunnerError("model_error", str(payload.get("result") or "claude returned error"))

    structured = payload.get("structured_output")
    if not isinstance(structured, dict):
        raise ClaudeRunnerError("invalid_json", "structured_output missing in claude response")

    return structured, latency_ms, _extract_model_name(payload)


def _build_findata(
    *,
    claude_bin: str,
    model: str,
    timeout_seconds: int,
    input_data: dict[str, Any],
) -> tuple[dict[str, Any], int, str]:
    schema = {
        "type": "object",
        "properties": {
            "macro_score": {"type": "number", "minimum": 0, "maximum": 100},
            "northbound_score": {"type": "number", "minimum": 0, "maximum": 100},
            "risk_hint": {"type": "string", "enum": ["risk_on", "neutral", "risk_off"]},
        },
        "required": ["macro_score", "northbound_score", "risk_hint"],
        "additionalProperties": False,
    }
    market = input_data.get("market") if isinstance(input_data.get("market"), dict) else {}
    prompt = (
        "You are a quantitative market assistant. "
        "Given this China A-share market snapshot JSON, produce one-day macro score and northbound score "
        "in range [0,100], plus a risk_hint enum.\n\n"
        f"market_json={json.dumps(market, ensure_ascii=False, default=str)}\n\n"
        "Rules:\n"
        "- Higher trend, breadth, and positive flows -> higher scores.\n"
        "- Weaker trend/flows and high risk -> lower scores.\n"
        "- risk_hint must be risk_on, neutral, or risk_off."
    )
    structured, latency_ms, model_name = _call_claude(
        claude_bin=claude_bin,
        model=model,
        prompt=prompt,
        schema=schema,
        timeout_seconds=timeout_seconds,
    )
    return {
        "macro_score": _clamp(_to_float(structured.get("macro_score"), 50.0), 0.0, 100.0),
        "northbound_score": _clamp(_to_float(structured.get("northbound_score"), 50.0), 0.0, 100.0),
        "risk_hint": str(structured.get("risk_hint") or "neutral"),
    }, latency_ms, model_name


def _summarize_stocks(stocks: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for item in stocks:
        if not isinstance(item, dict):
            continue
        industry = str(item.get("industry") or "").strip() or "UNKNOWN"
        score = _to_float(item.get("score"), 50.0)
        grouped[industry].append(score)

    industry_rows = []
    for industry, values in grouped.items():
        if not values:
            continue
        industry_rows.append(
            {
                "industry": industry,
                "count": len(values),
                "avg_score": round(sum(values) / len(values), 4),
            }
        )
    industry_rows.sort(key=lambda x: (float(x.get("avg_score") or 0.0), int(x.get("count") or 0)), reverse=True)

    score_values = [_to_float(item.get("score"), 50.0) for item in stocks if isinstance(item, dict)]
    avg_score = sum(score_values) / len(score_values) if score_values else 50.0
    return {
        "stock_count": len(stocks),
        "avg_input_score": round(avg_score, 4),
        "top_industries": industry_rows[:12],
    }


def _build_quant_factor(
    *,
    claude_bin: str,
    model: str,
    timeout_seconds: int,
    input_data: dict[str, Any],
) -> tuple[dict[str, Any], int, str]:
    stocks = input_data.get("stocks") if isinstance(input_data.get("stocks"), list) else []

    schema = {
        "type": "object",
        "properties": {
            "global_adjustment": {"type": "number", "minimum": -15, "maximum": 15},
            "industry_adjustments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "industry": {"type": "string"},
                        "adjustment": {"type": "number", "minimum": -10, "maximum": 10},
                    },
                    "required": ["industry", "adjustment"],
                    "additionalProperties": False,
                },
                "maxItems": 20,
            },
        },
        "required": ["global_adjustment", "industry_adjustments"],
        "additionalProperties": False,
    }

    summary = _summarize_stocks([item for item in stocks if isinstance(item, dict)])
    prompt = (
        "You are a low-frequency quant factor assistant. "
        "Given stock-score summary JSON, output a stable adjustment plan.\n\n"
        f"summary_json={json.dumps(summary, ensure_ascii=False, default=str)}\n\n"
        "Return conservative adjustments only, centered around 0."
    )

    structured, latency_ms, model_name = _call_claude(
        claude_bin=claude_bin,
        model=model,
        prompt=prompt,
        schema=schema,
        timeout_seconds=timeout_seconds,
    )

    global_adj = _to_float(structured.get("global_adjustment"), 0.0)
    industry_adj_map: dict[str, float] = {}
    for row in structured.get("industry_adjustments") or []:
        if not isinstance(row, dict):
            continue
        industry = str(row.get("industry") or "").strip()
        if not industry:
            continue
        industry_adj_map[industry] = _to_float(row.get("adjustment"), 0.0)

    rows: list[dict[str, Any]] = []
    for item in stocks:
        if not isinstance(item, dict):
            continue
        ts_code = _to_code(item.get("ts_code"))
        if not ts_code:
            continue
        base = _to_float(item.get("score"), 50.0)
        industry = str(item.get("industry") or "").strip() or "UNKNOWN"
        adjustment = global_adj + industry_adj_map.get(industry, 0.0)
        total_score = _clamp(base + adjustment, 0.0, 100.0)
        rows.append({"ts_code": ts_code, "total_score": round(total_score, 4)})

    return {"rows": rows}, latency_ms, model_name


def _build_sector_rotation(
    *,
    claude_bin: str,
    model: str,
    timeout_seconds: int,
    input_data: dict[str, Any],
) -> tuple[dict[str, Any], int, str]:
    industries = input_data.get("industries") if isinstance(input_data.get("industries"), list) else []
    cleaned_rows = []
    for item in industries:
        if not isinstance(item, dict):
            continue
        code = _to_code(item.get("industry_code"))
        if not code:
            continue
        cleaned_rows.append(
            {
                "industry_code": code,
                "rank": _to_float(item.get("rank"), 0.0),
                "rank_total": _to_float(item.get("rank_total"), 0.0),
                "pct_change": _to_float(item.get("pct_change"), 0.0),
            }
        )

    schema = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "industry_code": {"type": "string"},
                        "score": {"type": "number", "minimum": 0, "maximum": 100},
                        "bias": {"type": "string", "enum": ["overweight", "neutral", "underweight"]},
                    },
                    "required": ["industry_code", "score", "bias"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    }

    prompt = (
        "You are a sector-rotation assistant for China A-shares. "
        "Given industry momentum JSON with rank and pct_change, produce rotation scores [0,100] and bias labels.\n\n"
        f"industry_json={json.dumps(cleaned_rows, ensure_ascii=False, default=str)}\n\n"
        "Bias rule target:\n"
        "- stronger sectors should become overweight\n"
        "- mid sectors neutral\n"
        "- weakest sectors underweight"
    )

    structured, latency_ms, model_name = _call_claude(
        claude_bin=claude_bin,
        model=model,
        prompt=prompt,
        schema=schema,
        timeout_seconds=timeout_seconds,
    )

    output_rows: list[dict[str, Any]] = []
    for row in structured.get("rows") or []:
        if not isinstance(row, dict):
            continue
        code = _to_code(row.get("industry_code"))
        if not code:
            continue
        bias = str(row.get("bias") or "").strip().lower()
        if bias not in {"overweight", "neutral", "underweight"}:
            bias = "neutral"
        output_rows.append(
            {
                "industry_code": code,
                "score": round(_clamp(_to_float(row.get("score"), 50.0), 0.0, 100.0), 4),
                "bias": bias,
            }
        )

    if not output_rows and cleaned_rows:
        # deterministic fallback shape to avoid empty successful response
        ranked: list[tuple[str, float]] = []
        for item in cleaned_rows:
            total = _to_float(item.get("rank_total"), 0.0)
            rank = _to_float(item.get("rank"), 0.0)
            rank_score = 50.0 if total <= 1 else (1.0 - (rank - 1.0) / (total - 1.0)) * 100.0
            pct_score = _clamp((_to_float(item.get("pct_change"), 0.0) + 5.0) / 10.0, 0.0, 1.0) * 100.0
            ranked.append((str(item.get("industry_code") or ""), rank_score * 0.7 + pct_score * 0.3))
        ranked.sort(key=lambda x: x[1], reverse=True)
        top_n = max(int(math.ceil(len(ranked) * 0.2)), 1)
        bottom_n = max(int(math.ceil(len(ranked) * 0.2)), 1)
        for idx, (code, score) in enumerate(ranked):
            if idx < top_n:
                bias = "overweight"
            elif idx >= len(ranked) - bottom_n:
                bias = "underweight"
            else:
                bias = "neutral"
            output_rows.append({"industry_code": code, "score": round(score, 4), "bias": bias})

    return {"rows": output_rows}, latency_ms, model_name


class ClaudeAIRunnerHandler(BaseHTTPRequestHandler):
    token: str = ""
    claude_bin: str = "claude"
    model: str = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/", "/health"}:
            _json_response(self, {"ok": True, "service": "ai-runner-claude"})
            return
        _json_response(self, {"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.token:
            auth_header = str(self.headers.get("Authorization") or "")
            if auth_header != f"Bearer {self.token}":
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

        payload = _read_json(self)
        request_id = str(payload.get("request_id") or "")
        timeout_sec = int(_clamp(_to_float(payload.get("timeout_sec"), 90.0), 5.0, 300.0))
        input_data = payload.get("input") if isinstance(payload.get("input"), dict) else {}

        skill_name = self.path.split("/v1/skills/", 1)[-1].strip("/")
        try:
            if skill_name == "findata-toolkit-cn":
                data, latency_ms, model_name = _build_findata(
                    claude_bin=self.claude_bin,
                    model=self.model,
                    timeout_seconds=timeout_sec,
                    input_data=input_data,
                )
            elif skill_name == "quant-factor-screener":
                data, latency_ms, model_name = _build_quant_factor(
                    claude_bin=self.claude_bin,
                    model=self.model,
                    timeout_seconds=timeout_sec,
                    input_data=input_data,
                )
            elif skill_name == "sector-rotation-detector":
                data, latency_ms, model_name = _build_sector_rotation(
                    claude_bin=self.claude_bin,
                    model=self.model,
                    timeout_seconds=timeout_sec,
                    input_data=input_data,
                )
            else:
                _json_response(
                    self,
                    {
                        "ok": False,
                        "status": "invalid_json",
                        "error": f"unsupported skill: {skill_name}",
                        "request_id": request_id,
                        "data": None,
                        "latency_ms": 0,
                        "model": "",
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
                    "latency_ms": latency_ms,
                    "model": model_name,
                },
            )
        except ClaudeRunnerError as exc:
            _json_response(
                self,
                {
                    "ok": False,
                    "status": exc.code,
                    "error": exc.message,
                    "request_id": request_id,
                    "data": None,
                    "latency_ms": 0,
                    "model": "",
                },
            )
        except Exception as exc:
            _json_response(
                self,
                {
                    "ok": False,
                    "status": "upstream_error",
                    "error": str(exc),
                    "request_id": request_id,
                    "data": None,
                    "latency_ms": 0,
                    "model": "",
                },
            )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude-based AI Runner service for Freedom")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18600)
    parser.add_argument("--token", type=str, default="")
    parser.add_argument("--claude-bin", type=str, default="claude")
    parser.add_argument("--model", type=str, default="")
    args = parser.parse_args()

    ClaudeAIRunnerHandler.token = str(args.token or "").strip()
    ClaudeAIRunnerHandler.claude_bin = str(args.claude_bin or "claude").strip() or "claude"
    ClaudeAIRunnerHandler.model = str(args.model or "").strip()

    server = ThreadingHTTPServer((args.host, args.port), ClaudeAIRunnerHandler)
    print(f"[ai-runner-claude] listening on http://{args.host}:{args.port}")
    print("[ai-runner-claude] endpoints: /health and /v1/skills/{findata-toolkit-cn|quant-factor-screener|sector-rotation-detector}")
    if ClaudeAIRunnerHandler.model:
        print(f"[ai-runner-claude] model={ClaudeAIRunnerHandler.model}")
    else:
        print("[ai-runner-claude] model=default")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
