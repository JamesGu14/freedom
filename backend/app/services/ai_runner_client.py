from __future__ import annotations

import json
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from app.core.config import settings


class AIRunnerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class SkillCallResult:
    request_id: str
    skill_name: str
    ok: bool
    status: str
    data: dict[str, Any] | None
    error: str
    latency_ms: int
    attempts: int
    model: str


_ALLOWED_STATUS = {
    "success",
    "timeout",
    "auth_error",
    "model_error",
    "invalid_json",
    "upstream_error",
}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_findata_payload(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise AIRunnerError("invalid_json", "findata payload must be object")
    if _to_float(data.get("macro_score")) is None:
        raise AIRunnerError("invalid_json", "findata.macro_score missing")
    if _to_float(data.get("northbound_score")) is None:
        raise AIRunnerError("invalid_json", "findata.northbound_score missing")
    risk_hint = str(data.get("risk_hint") or "").strip()
    if not risk_hint:
        raise AIRunnerError("invalid_json", "findata.risk_hint missing")


def _validate_quant_factor_payload(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise AIRunnerError("invalid_json", "quant-factor payload must be object")
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise AIRunnerError("invalid_json", "quant-factor.rows missing")
    for row in rows:
        if not isinstance(row, dict):
            raise AIRunnerError("invalid_json", "quant-factor row must be object")
        ts_code = str(row.get("ts_code") or "").strip()
        if not ts_code:
            raise AIRunnerError("invalid_json", "quant-factor row.ts_code missing")
        if _to_float(row.get("total_score")) is None:
            raise AIRunnerError("invalid_json", "quant-factor row.total_score missing")


def _validate_sector_rotation_payload(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise AIRunnerError("invalid_json", "sector-rotation payload must be object")
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise AIRunnerError("invalid_json", "sector-rotation.rows missing")
    for row in rows:
        if not isinstance(row, dict):
            raise AIRunnerError("invalid_json", "sector-rotation row must be object")
        industry_code = str(row.get("industry_code") or "").strip()
        if not industry_code:
            raise AIRunnerError("invalid_json", "sector-rotation row.industry_code missing")
        if _to_float(row.get("score")) is None:
            raise AIRunnerError("invalid_json", "sector-rotation row.score missing")
        bias = str(row.get("bias") or "").strip().lower()
        if bias not in {"overweight", "neutral", "underweight"}:
            raise AIRunnerError("invalid_json", "sector-rotation row.bias invalid")


def _validate_skill_payload(skill_name: str, data: dict[str, Any]) -> None:
    if skill_name == "findata-toolkit-cn":
        _validate_findata_payload(data)
        return
    if skill_name == "quant-factor-screener":
        _validate_quant_factor_payload(data)
        return
    if skill_name == "sector-rotation-detector":
        _validate_sector_rotation_payload(data)
        return
    raise AIRunnerError("invalid_json", f"unsupported skill_name: {skill_name}")


def _parse_response_body(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise AIRunnerError("invalid_json", f"response decode failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise AIRunnerError("invalid_json", "response must be object")
    return payload


def _post_json(*, url: str, payload: dict[str, Any], token: str, timeout_seconds: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout_seconds) as resp:
        return _parse_response_body(resp.read())


def call_skill(
    *,
    skill_name: str,
    trade_date: str,
    input_payload: dict[str, Any],
    request_id: str | None = None,
) -> SkillCallResult:
    request_id = request_id or uuid.uuid4().hex
    base_url = str(settings.ai_runner_base_url or "").strip().rstrip("/")
    if not base_url:
        raise AIRunnerError("upstream_error", "AI_RUNNER_BASE_URL is empty")
    url = f"{base_url}/v1/skills/{skill_name}"

    timeout_seconds = max(int(settings.ai_runner_timeout_seconds), 1)
    max_retries = max(int(settings.ai_runner_max_retries), 0)
    attempts = 0
    last_error = ""
    last_code = "upstream_error"

    while attempts <= max_retries:
        attempts += 1
        started = time.perf_counter()
        try:
            response = _post_json(
                url=url,
                payload={
                    "request_id": request_id,
                    "trade_date": trade_date,
                    "timeout_sec": timeout_seconds,
                    "input": input_payload,
                },
                token=str(settings.ai_runner_token or "").strip(),
                timeout_seconds=timeout_seconds,
            )
            ok = bool(response.get("ok"))
            status = str(response.get("status") or "").strip()
            if status not in _ALLOWED_STATUS:
                raise AIRunnerError("invalid_json", f"invalid status: {status}")
            if not ok:
                error_text = str(response.get("error") or "skill call failed").strip()
                raise AIRunnerError(status or "upstream_error", error_text)
            data = response.get("data")
            if not isinstance(data, dict):
                raise AIRunnerError("invalid_json", "response.data must be object")
            _validate_skill_payload(skill_name, data)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SkillCallResult(
                request_id=request_id,
                skill_name=skill_name,
                ok=True,
                status="success",
                data=data,
                error="",
                latency_ms=latency_ms,
                attempts=attempts,
                model=str(response.get("model") or ""),
            )
        except AIRunnerError as exc:
            last_error = exc.message
            last_code = exc.code
            retryable = exc.code in {"timeout", "upstream_error", "model_error"}
            if attempts > max_retries or not retryable:
                break
        except error.HTTPError as exc:
            code = "auth_error" if exc.code in {401, 403} else "upstream_error"
            last_error = f"http_error:{exc.code}"
            last_code = code
            retryable = code != "auth_error"
            if attempts > max_retries or not retryable:
                break
        except (socket.timeout, TimeoutError):
            last_error = "timeout"
            last_code = "timeout"
            if attempts > max_retries:
                break
        except error.URLError as exc:
            last_error = f"url_error:{exc.reason}"
            last_code = "upstream_error"
            if attempts > max_retries:
                break
        except Exception as exc:
            last_error = str(exc)
            last_code = "upstream_error"
            if attempts > max_retries:
                break

    return SkillCallResult(
        request_id=request_id,
        skill_name=skill_name,
        ok=False,
        status=last_code,
        data=None,
        error=last_error,
        latency_ms=0,
        attempts=attempts,
        model="",
    )
