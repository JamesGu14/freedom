from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY_MINUTES = 10


@dataclass(frozen=True)
class DailySyncTask:
    task_id: str
    group: str
    script_path: str
    base_args: tuple[str, ...] = field(default_factory=tuple)
    append_trade_date_range: bool = True
    timeout_seconds: int = 7200
    retries: int = DEFAULT_RETRIES
    retry_delay_minutes: int = DEFAULT_RETRY_DELAY_MINUTES
    critical: bool = False

    def render_command(self, trade_date: str) -> list[str]:
        command = [
            "python",
            self.script_path,
            *self.base_args,
        ]
        if self.append_trade_date_range:
            command.extend(
                [
                    "--start-date",
                    trade_date,
                    "--end-date",
                    trade_date,
                ]
            )
        return command


DAILY_SYNC_TASKS: tuple[DailySyncTask, ...] = (
    DailySyncTask(
        task_id="pull_daily_history",
        group="market_core",
        script_path="backend/scripts/daily/pull_daily_history.py",
        critical=True,
    ),
    DailySyncTask(
        task_id="sync_suspend_d",
        group="market_core",
        script_path="backend/scripts/daily/sync_suspend_d.py",
    ),
    DailySyncTask(
        task_id="sync_stk_factor_pro",
        group="factor_and_flow",
        script_path="backend/scripts/daily/sync_stk_factor_pro.py",
        critical=True,
    ),
    DailySyncTask(
        task_id="sync_cyq_perf",
        group="factor_and_flow",
        script_path="backend/scripts/daily/sync_cyq_perf.py",
        critical=True,
    ),
    DailySyncTask(
        task_id="sync_moneyflow_dc",
        group="factor_and_flow",
        script_path="backend/scripts/daily/sync_moneyflow_dc.py",
    ),
    DailySyncTask(
        task_id="sync_moneyflow_hsgt",
        group="factor_and_flow",
        script_path="backend/scripts/daily/sync_moneyflow_hsgt.py",
    ),
    DailySyncTask(
        task_id="sync_income",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_financial_reports.py",
        base_args=("--dataset", "income"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_balancesheet",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_financial_reports.py",
        base_args=("--dataset", "balancesheet"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_cashflow",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_financial_reports.py",
        base_args=("--dataset", "cashflow"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_fina_indicator",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_financial_reports.py",
        base_args=("--dataset", "fina_indicator"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_forecast",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_financial_reports.py",
        base_args=("--dataset", "forecast"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_express",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_financial_reports.py",
        base_args=("--dataset", "express"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_fina_audit",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_fina_audit.py",
        base_args=("--mode", "daily", "--last-days", "30", "--sleep", "0"),
        timeout_seconds=14400,
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_disclosure_date",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_disclosure_date.py",
        base_args=("--recent", "2"),
        append_trade_date_range=False,
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_dividend",
        group="financials_and_corporate",
        script_path="backend/scripts/daily/sync_dividend.py",
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_holdernumber",
        group="holders_and_margin",
        script_path="backend/scripts/daily/sync_holdernumber.py",
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_top10_holders",
        group="holders_and_margin",
        script_path="backend/scripts/daily/sync_top10_holders.py",
        base_args=("--dataset", "top10_holders"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_top10_floatholders",
        group="holders_and_margin",
        script_path="backend/scripts/daily/sync_top10_holders.py",
        base_args=("--dataset", "top10_floatholders"),
        retries=3,
        retry_delay_minutes=15,
    ),
    DailySyncTask(
        task_id="sync_margin",
        group="holders_and_margin",
        script_path="backend/scripts/daily/sync_margin.py",
    ),
    DailySyncTask(
        task_id="sync_margin_detail",
        group="holders_and_margin",
        script_path="backend/scripts/daily/sync_margin_detail.py",
    ),
    DailySyncTask(
        task_id="sync_index_daily",
        group="index_and_industry",
        script_path="backend/scripts/daily/sync_index_daily.py",
    ),
    DailySyncTask(
        task_id="sync_shenwan_daily",
        group="index_and_industry",
        script_path="backend/scripts/daily/sync_shenwan_daily.py",
    ),
    DailySyncTask(
        task_id="sync_zhishu_daily_bundle",
        group="index_and_industry",
        script_path="backend/scripts/daily/sync_zhishu_data.py",
        base_args=("--modules", "all", "--skip-members"),
    ),
    DailySyncTask(
        task_id="generate_daily_stock_signals",
        group="signals_and_screeners",
        script_path="backend/scripts/daily/generate_daily_stock_signals.py",
    ),
    DailySyncTask(
        task_id="generate_market_regime",
        group="signals_and_screeners",
        script_path="backend/scripts/daily/generate_market_regime.py",
    ),
)


_TASK_INDEX = {task.task_id: task for task in DAILY_SYNC_TASKS}


def get_daily_sync_task(task_id: str) -> DailySyncTask:
    return _TASK_INDEX[task_id]
