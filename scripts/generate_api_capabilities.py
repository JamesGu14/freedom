#!/usr/bin/env python3
"""Generate a human-readable API capabilities document from the OpenAPI spec.

Output: docs/api-capabilities.md
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPENAPI_PATH = os.path.join(PROJECT_ROOT, "docs", "openapi.json")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "docs", "api-capabilities.md")


def extract_path_group(path: str) -> str:
    """Group API paths by their logical domain."""
    path_lower = path.lower().replace("/api/", "").strip("/")
    segments = path_lower.split("/")
    if not segments or segments == [""]:
        return "通用"

    first = segments[0]

    # Multi-segment market-data endpoints are grouped by their functional area.
    market_data_prefixes = {
        "ccass-hold", "chip-distribution", "chip-perf", "hk-hold",
        "index-factors", "institution-survey", "moneyflow-dc", "moneyflow-hsgt",
    }
    if first in market_data_prefixes:
        return "市场数据"

    group_mapping = {
        "health": "系统",
        "auth": "认证",
        "stocks": "股票基础",
        "stock-groups": "自选股分组",
        "daily-signals": "每日信号",
        "daily-stock-signals": "每日股票信号",
        "strategy-signals": "策略信号",
        "strategies": "策略管理",
        "backtests": "回测",
        "market-index": "市场指数",
        "market-regime": "市场状态",
        "market-data": "市场数据",
        "market": "市场研究",
        "sector-ranking": "板块排名",
        "sectors": "行业板块",
        "shenwan-industries": "申万行业",
        "shenwan-members": "申万行业",
        "citic-sectors": "中信行业",
        "industry": "行业数据",
        "research": "综合研究",
        "trade-calendar": "交易日历",
        "macro": "宏观数据",
        "data-sync": "数据同步",
        "internal": "内部审计",
        "users": "用户管理",
        "agent-freedom": "Agent Freedom",
        "signal": "旧版信号",
    }
    return group_mapping.get(first, first)


def describe_param(param: dict) -> str:
    name = param.get("name", "")
    required = param.get("required", False)
    schema = param.get("schema", {})
    ptype = schema.get("type", "")
    enum = schema.get("enum")
    default = schema.get("default")
    description = param.get("description", "")

    parts = [f"`{name}`"]
    if required:
        parts.append("*必填*")
    else:
        parts.append("可选")
    if ptype:
        parts.append(f"`{ptype}`")
    if enum:
        parts.append(f"可选值: {', '.join(str(e) for e in enum)}")
    if default is not None:
        parts.append(f"默认: `{default}`")
    if description:
        parts.append(f"— {description}")
    return " ".join(parts)


def generate() -> None:
    with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
        spec = json.load(f)

    info = spec.get("info", {})
    paths = spec.get("paths", {})

    groups = defaultdict(list)
    for path, methods in paths.items():
        for method, detail in methods.items():
            if method.lower() in ("parameters",):
                continue
            group = extract_path_group(path)
            groups[group].append(
                {
                    "path": path,
                    "method": method.upper(),
                    "summary": detail.get("summary", ""),
                    "description": detail.get("description", ""),
                    "parameters": detail.get("parameters", []),
                }
            )

    # Sort groups and endpoints within each group for stable output.
    sorted_groups = dict(sorted(groups.items(), key=lambda x: x[0]))
    for group in sorted_groups:
        sorted_groups[group].sort(key=lambda x: (x["path"], x["method"]))

    lines = [
        "# Freedom Quant Platform - API 能力范围（Scope）",
        "",
        f"**版本**: {info.get('version', 'unknown')}",
        f"**标题**: {info.get('title', 'Freedom Quant Platform')}",
        "",
        "本文档面向 AI Agent（如 KimiClaw）快速理解 Freedom 后端 API 的能力边界。",
        "如需精确参数和返回结构，请同时参考 `docs/openapi.yaml` 或 `docs/openapi.json`。",
        "",
        "## 认证方式",
        "",
        "除 `/api/health` 和 `/api/auth/*` 外，其余接口通常需要 `Authorization: Bearer <token>`。",
        "",
        "## 能力地图（按业务域分组）",
        "",
    ]

    for group, endpoints in sorted_groups.items():
        lines.append(f"### {group}")
        lines.append("")
        for ep in endpoints:
            summary = ep["summary"] or ep["description"] or "未提供描述"
            lines.append(f"- **{ep['method']}** `{ep['path']}` — {summary}")
            if ep["parameters"]:
                for param in ep["parameters"]:
                    if "in" in param and param["in"] in ("query", "path"):
                        lines.append(f"  - {describe_param(param)}")
        lines.append("")

    lines.extend(
        [
            "## 典型使用场景",
            "",
            "1. **查股票/行情**: `search_stocks` → `get_stock_basic` / `get_stock_daily` / `get_stock_indicators`",
            "2. **看行业/板块**: `get_shenwan_industry_tree` / `get_sector_ranking` / `get_citic_members`",
            "3. **财务筛选**: `screen_financials` / `screen_dividends` / `screen_stocks_by_valuation`",
            "4. **交易信号**: `get_daily_signals` / `get_daily_stock_signals_overview` / `get_strategy_signals`",
            "5. **回测验证**: `create_backtest` → `get_backtest` / `get_backtest/{run_id}/nav` / `trades`",
            "6. **深度研究**: `get_stock_overview` / `get_stock_chips` / `get_stock_moneyflow` / `get_stock_events`",
            "7. **宏观/市场**: `get_market_regime` / `get_market_data_overview` / `get_macro_*`",
            "8. **任务/管理**: `list_stock_groups` / `create_stock_group` / `add_stock_to_group`",
            "",
            "## 给 AI Agent 的提示",
            "",
            "- 股票代码使用 `ts_code` 格式，如 `600519.SH`、`000001.SZ`。",
            "- 日期格式多为 `YYYYMMDD` 或 `YYYY-MM-DD`。",
            "- 分页参数通常是 `page` / `page_size`。",
            "- 涉及 `PUT/POST/DELETE` 的操作可能修改用户数据，调用前建议确认。",
            "",
        ]
    )

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generated API capabilities doc at {OUTPUT_PATH}")
    print(f"  Groups: {len(sorted_groups)}")
    print(f"  Endpoints: {sum(len(v) for v in sorted_groups.values())}")


if __name__ == "__main__":
    generate()
