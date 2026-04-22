from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import tushare as ts

from app.core.config import settings
from app.data.duckdb_store import upsert_adj_factor
from app.data.mongo_market_index import DEFAULT_MARKET_INDEX_CODES
from app.data.tushare_client import fetch_adj_factor, fetch_moneyflow_dc
from scripts.daily.sync_moneyflow_dc import save_moneyflow_dc, transform_df as transform_moneyflow_dc_df
from scripts.daily.sync_zhishu_data import sync_index_factors_for_trade_date


@dataclass(slots=True)
class RepairTarget:
    dataset: str
    storage_type: str
    repair_dates: list[str]


def extract_repair_dates(dataset_summary: dict[str, object]) -> list[str]:
    dates: set[str] = set()

    date_gap = dataset_summary.get("date_gap") or {}
    for value in date_gap.get("missing_trade_dates", []):
        if value:
            dates.add(str(value))

    for row in dataset_summary.get("coverage_anomalies", []):
        trade_date = row.get("trade_date")
        if trade_date:
            dates.add(str(trade_date))

    for row in dataset_summary.get("rowcount_anomalies", []):
        trade_date = row.get("trade_date")
        if trade_date:
            dates.add(str(trade_date))

    return sorted(dates)


P0_DATASET_CONFIG: dict[str, dict[str, str]] = {
    "moneyflow_dc": {"storage_type": "parquet"},
    "adj_factor": {"storage_type": "parquet"},
    "index_factor_pro": {"storage_type": "mongo"},
}


def load_audit_summary(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_p0_targets(
    summary: dict[str, object],
    selected_datasets: list[str] | None = None,
) -> dict[str, RepairTarget]:
    targets: dict[str, RepairTarget] = {}
    allowed = set(selected_datasets or P0_DATASET_CONFIG.keys())
    for dataset_summary in summary.get("datasets", []):
        dataset_name = dataset_summary.get("dataset")
        if dataset_name not in P0_DATASET_CONFIG or dataset_name not in allowed:
            continue
        targets[str(dataset_name)] = RepairTarget(
            dataset=str(dataset_name),
            storage_type=P0_DATASET_CONFIG[str(dataset_name)]["storage_type"],
            repair_dates=extract_repair_dates(dataset_summary),
        )
    return targets


def repair_moneyflow_dc_date(trade_date: str) -> dict[str, object]:
    raw_df = fetch_moneyflow_dc(trade_date=trade_date)
    if raw_df is None or raw_df.empty:
        return {"dataset": "moneyflow_dc", "trade_date": trade_date, "status": "no_data", "rows": 0}

    normalized_df = transform_moneyflow_dc_df(raw_df, trade_date)
    if normalized_df.empty:
        return {"dataset": "moneyflow_dc", "trade_date": trade_date, "status": "empty_after_transform", "rows": 0}

    saved = save_moneyflow_dc(normalized_df)
    return {
        "dataset": "moneyflow_dc",
        "trade_date": trade_date,
        "status": "success",
        "rows": int(saved),
        "stocks": int(normalized_df["ts_code"].nunique()),
    }


def repair_adj_factor_date(trade_date: str) -> dict[str, object]:
    raw_df = fetch_adj_factor(trade_date=trade_date)
    if raw_df is None or raw_df.empty:
        return {"dataset": "adj_factor", "trade_date": trade_date, "status": "no_data", "rows": 0}

    saved = upsert_adj_factor(raw_df)
    return {"dataset": "adj_factor", "trade_date": trade_date, "status": "success", "rows": int(saved)}


def repair_adj_factor_dates(trade_dates: list[str]) -> list[dict[str, object]]:
    if not trade_dates:
        return []

    results: list[dict[str, object]] = []
    for trade_date in trade_dates:
        try:
            raw_df = fetch_adj_factor(trade_date=trade_date)
        except ValueError as exc:
            if "IP数量超限" not in str(exc):
                raise
            raw_df = _fetch_adj_factor_via_tushare(trade_date)
        if raw_df is None or raw_df.empty:
            results.append({"dataset": "adj_factor", "trade_date": trade_date, "status": "no_data", "rows": 0})
            continue

        saved = upsert_adj_factor(raw_df)
        results.append(
            {
                "dataset": "adj_factor",
                "trade_date": trade_date,
                "status": "success",
                "rows": int(saved),
            }
        )

    results.sort(key=lambda row: str(row["trade_date"]))
    return results


def repair_index_factor_pro_date(trade_date: str) -> dict[str, object]:
    upserted, counts = sync_index_factors_for_trade_date(
        trade_date=trade_date,
        target_codes_by_source={
            "market": set(DEFAULT_MARKET_INDEX_CODES),
            "ci": set(),
            "sw": set(),
        },
        sleep_seconds=0,
    )
    status = "success" if upserted > 0 else "no_data"
    return {
        "dataset": "index_factor_pro",
        "trade_date": trade_date,
        "status": status,
        "rows": int(upserted),
        "source_counts": counts,
    }


def repair_trade_date(dataset: str, trade_date: str) -> dict[str, object]:
    if dataset == "moneyflow_dc":
        return repair_moneyflow_dc_date(trade_date)
    if dataset == "adj_factor":
        return repair_adj_factor_date(trade_date)
    if dataset == "index_factor_pro":
        return repair_index_factor_pro_date(trade_date)
    raise ValueError(f"unsupported dataset: {dataset}")


def assess_compaction_need(targets: dict[str, RepairTarget]) -> dict[str, dict[str, object]]:
    recommendations: dict[str, dict[str, object]] = {}
    for dataset_name, target in targets.items():
        if target.storage_type == "mongo":
            recommendations[dataset_name] = {"should_run": False, "reason": "mongo_dataset"}
        elif target.storage_type == "parquet":
            recommendations[dataset_name] = {"should_run": True, "reason": "parquet_dataset_after_repair"}
        else:
            recommendations[dataset_name] = {"should_run": False, "reason": "unsupported_storage_type"}
    return recommendations


def run_repairs(targets: dict[str, RepairTarget]) -> dict[str, list[dict[str, object]]]:
    results: dict[str, list[dict[str, object]]] = {}
    for dataset_name, target in targets.items():
        if dataset_name == "adj_factor":
            try:
                results[dataset_name] = repair_adj_factor_dates(target.repair_dates)
            except Exception as exc:  # noqa: BLE001
                results[dataset_name] = [
                    {
                        "dataset": dataset_name,
                        "trade_date": trade_date,
                        "status": "error",
                        "rows": 0,
                        "error": str(exc),
                    }
                    for trade_date in target.repair_dates
                ]
            continue

        rows: list[dict[str, object]] = []
        for trade_date in target.repair_dates:
            try:
                rows.append(repair_trade_date(dataset_name, trade_date))
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "dataset": dataset_name,
                        "trade_date": trade_date,
                        "status": "error",
                        "rows": 0,
                        "error": str(exc),
                    }
                )
        results[dataset_name] = rows
    return results


def _fetch_adj_factor_via_tushare(trade_date: str):
    pro = ts.pro_api(settings.tushare_token)
    return pro.adj_factor(trade_date=trade_date)
