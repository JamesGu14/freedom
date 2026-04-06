from __future__ import annotations

import json
import time
from typing import Any
from urllib import error, request

from app.core.config import settings


def build_daily_report_markdown(
    *,
    trade_date: str,
    regime: str,
    regime_reason: str,
    degrade_flags: list[str],
    buy_items: list[dict[str, Any]],
    sell_items: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
    industry_top: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append(f"Caishenye Daily Report {trade_date}")
    lines.append(f"Market Regime: {regime}")
    if regime_reason:
        lines.append(f"Regime Reason: {regime_reason}")
    lines.append(f"Degrade Flags: {'; '.join(degrade_flags) if degrade_flags else 'none'}")
    lines.append("")

    lines.append("[Industry Allocation Top6]")
    if industry_top:
        for item in industry_top[:6]:
            lines.append(
                f"- {item.get('industry_name') or item.get('industry_code')} | score {float(item.get('score') or 0):.2f} | {item.get('allocation_tag') or '-'}"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("[Buy Candidates Top10]")
    if buy_items:
        for idx, item in enumerate(buy_items[:10], start=1):
            lines.append(
                f"{idx}. {item.get('ts_code')} {item.get('stock_name') or ''} | {item.get('signal')} | score {float(item.get('score') or 0):.2f}"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("[Sell Suggestions]")
    if sell_items:
        for idx, item in enumerate(sell_items[:10], start=1):
            lines.append(
                f"{idx}. {item.get('ts_code')} {item.get('stock_name') or ''} | {item.get('signal')} | score {float(item.get('score') or 0):.2f}"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("[Risk Board]")
    if risk_items:
        for item in risk_items[:20]:
            lines.append(
                f"- {item.get('ts_code')} | {item.get('rule_code')} | {item.get('action')} | {item.get('detail') or ''}"
            )
    else:
        lines.append("- no risk trigger")

    lines.append("")
    lines.append("Disclaimer: This report is for reference only and is not investment advice.")
    return "\n".join(lines)


def push_feishu_text(message: str) -> dict[str, Any]:
    webhook = str(settings.feishu_webhook_url or "").strip()
    if not webhook:
        return {"status": "skipped", "reason": "feishu_webhook_not_configured"}

    body = {
        "msg_type": "text",
        "content": {"text": message},
    }
    req = request.Request(
        url=webhook,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )

    retry_waits = [10, 30, 60]
    for idx, wait_seconds in enumerate(retry_waits, start=1):
        try:
            with request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw)
                code = int(payload.get("code", -1))
                if code == 0:
                    return {"status": "success", "attempts": idx, "detail": payload}
                if idx == len(retry_waits):
                    return {
                        "status": "failed",
                        "attempts": idx,
                        "reason": f"feishu_error_code:{code}",
                        "detail": payload,
                    }
        except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
            if idx == len(retry_waits):
                return {"status": "failed", "attempts": idx, "reason": str(exc)}
        except Exception as exc:
            if idx == len(retry_waits):
                return {"status": "failed", "attempts": idx, "reason": str(exc)}

        time.sleep(wait_seconds)

    return {"status": "failed", "reason": "unknown"}
