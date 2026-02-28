from __future__ import annotations

from typing import Any

from app.data.mongo_backtest import (
    create_backtest_run,
    delete_backtest_run,
    get_backtest_run,
    get_strategy_definition,
    get_strategy_version,
    list_backtest_drawdown,
    list_backtest_holdings_summary,
    list_backtest_nav,
    list_backtest_positions,
    list_backtest_runs,
    list_backtest_runs_by_ids,
    list_backtest_signals,
    list_backtest_trades_by_code,
    list_backtest_trades,
)


def create_backtest_run_meta(
    *,
    strategy_id: str,
    strategy_version_id: str,
    start_date: str,
    end_date: str,
    run_type: str = "range",
    initial_capital: float = 1_000_000.0,
    created_by: str = "",
    run_id: str | None = None,
) -> dict[str, Any]:
    strategy = get_strategy_definition(strategy_id)
    if not strategy:
        raise ValueError("strategy not found")
    strategy_key = str(strategy.get("strategy_key") or "").strip() or "multifactor_v1"
    version = get_strategy_version(strategy_version_id)
    if not version:
        raise ValueError("strategy version not found")
    if str(version.get("strategy_id")) != strategy_id:
        raise ValueError("strategy_version_id does not belong to strategy_id")
    version_key = str(version.get("strategy_key") or "").strip() or "multifactor_v1"
    if version_key != strategy_key:
        raise ValueError("strategy_key mismatch between strategy definition and strategy version")
    return create_backtest_run(
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        strategy_key=strategy_key,
        start_date=start_date,
        end_date=end_date,
        run_type=run_type,
        initial_capital=initial_capital,
        params_snapshot=dict(version.get("params_snapshot") or {}),
        created_by=created_by or "",
        run_id=run_id,
    )


def list_backtests(
    *,
    page: int = 1,
    page_size: int = 20,
    strategy_id: str | None = None,
    strategy_version_id: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    items, total = list_backtest_runs(
        page=page,
        page_size=page_size,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        status=status,
    )
    for item in items:
        version_id = str(item.get("strategy_version_id") or "")
        if not version_id:
            continue
        version = get_strategy_version(version_id)
        if not version:
            continue
        item["strategy_version"] = version
        item["change_log"] = str(version.get("change_log") or "")
    return items, total


def get_backtest_detail(run_id: str) -> dict[str, Any] | None:
    run = get_backtest_run(run_id)
    if not run:
        return None
    strategy = get_strategy_definition(str(run.get("strategy_id") or ""))
    version = get_strategy_version(str(run.get("strategy_version_id") or ""))
    run["strategy"] = strategy
    run["strategy_version"] = version
    return run


def get_backtest_nav(run_id: str) -> list[dict[str, Any]]:
    return list_backtest_nav(run_id=run_id)


def get_backtest_drawdown(run_id: str) -> list[dict[str, Any]]:
    return list_backtest_drawdown(run_id=run_id)


def get_backtest_trades(
    *,
    run_id: str,
    page: int = 1,
    page_size: int = 20,
    ts_code: str | None = None,
    trade_date: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    return list_backtest_trades(
        run_id=run_id,
        page=page,
        page_size=page_size,
        ts_code=ts_code,
        trade_date=trade_date,
    )


def get_backtest_trades_by_code(
    *,
    run_id: str,
    ts_code: str,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    return list_backtest_trades_by_code(run_id=run_id, ts_code=ts_code, limit=limit)


def get_backtest_positions(
    *,
    run_id: str,
    page: int = 1,
    page_size: int = 20,
    trade_date: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    return list_backtest_positions(
        run_id=run_id,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
    )


def get_backtest_holdings_summary(run_id: str) -> list[dict[str, Any]]:
    return list_backtest_holdings_summary(run_id)


def get_backtest_signals(
    *,
    run_id: str,
    page: int = 1,
    page_size: int = 20,
    trade_date: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    return list_backtest_signals(
        run_id=run_id,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
    )


def compare_backtests(run_ids: list[str]) -> list[dict[str, Any]]:
    runs = list_backtest_runs_by_ids(run_ids)
    items: list[dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        nav_series = list_backtest_nav(run_id=run_id)
        items.append(
            {
                "run_id": run_id,
                "strategy_id": run.get("strategy_id"),
                "strategy_version_id": run.get("strategy_version_id"),
                "status": run.get("status"),
                "summary_metrics": run.get("summary_metrics") or {},
                "nav_series": nav_series,
            }
        )
    return items


def delete_backtest_run_meta(run_id: str) -> bool:
    run = get_backtest_run(run_id)
    if not run:
        return False
    return delete_backtest_run(run_id)
