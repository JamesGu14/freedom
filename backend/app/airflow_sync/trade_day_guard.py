from __future__ import annotations

from app.airflow_sync.host_job_runner import SshConnectionConfig, build_host_python_command, run_ssh_command


def normalize_trade_date(value: str) -> str:
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid trade date: {value}")
    return text


def parse_trade_day_check_output(output: str) -> bool:
    return str(output).strip() == "1"


def is_trade_day(trade_date: str, *, config: SshConnectionConfig | None = None) -> bool:
    normalized = normalize_trade_date(trade_date)
    python_code = (
        "from app.data.mongo_trade_calendar import is_trading_day;"
        f" print('1' if is_trading_day('{normalized}', exchange='SSE') else '0')"
    )
    remote_command = build_host_python_command(python_code)
    exit_status, stdout, stderr = run_ssh_command(config or SshConnectionConfig.from_env(), remote_command, timeout_seconds=120)
    if exit_status != 0:
        raise RuntimeError(f"trade-day guard failed: {stderr.strip()}")
    return parse_trade_day_check_output(stdout)

