from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.request
from typing import Any


FEISHU_WEBHOOK_URL = (
    "https://open.feishu.cn/open-apis/bot/v2/hook/"
    "6aed1a48-cc24-496a-84e2-df17ce214f36"
)
FEISHU_SIGNATURE_SECRET = "E7fpEuRyTeETv3awZHGRzh"


def _generate_sign(secret: str, timestamp: int) -> str:
    """Generate Feishu webhook signature."""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu_alert(title: str, content: str) -> dict[str, Any]:
    """Send alert message to Feishu bot.

    Args:
        title: Message title (will be prepended to content).
        content: Markdown-formatted message content.

    Returns:
        Feishu API response parsed as dict.
    """
    timestamp = int(time.time())
    sign = _generate_sign(FEISHU_SIGNATURE_SECRET, timestamp)

    payload = {
        "timestamp": str(timestamp),
        "sign": sign,
        "msg_type": "text",
        "content": {"text": f"{title}\n\n{content}"},
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=FEISHU_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}
