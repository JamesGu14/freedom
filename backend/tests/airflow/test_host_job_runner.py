from __future__ import annotations

from app.airflow_sync.host_job_runner import (
    HostJobRequest,
    SshConnectionConfig,
    build_host_python_command,
    build_host_runner_command,
)


def test_build_host_runner_command_renders_expected_shell_invocation() -> None:
    request = HostJobRequest(
        dag_id="freedom_market_data_daily",
        task_id="sync_dividend",
        run_id="manual__20260315T123000",
        trade_date="20260315",
        command=["python", "backend/scripts/daily/sync_dividend.py", "--start-date", "20260315", "--end-date", "20260315"],
    )

    command = build_host_runner_command(request)

    assert "/home/james/projects/freedom/scripts/run_freedom_sync_job.sh" in command
    assert "--dag-id freedom_market_data_daily" in command
    assert "--task-id sync_dividend" in command
    assert "--run-id manual__20260315T123000" in command
    assert "--trade-date 20260315" in command
    assert "backend/scripts/daily/sync_dividend.py" in command


def test_build_host_runner_command_uses_shell_safe_quoting_for_args() -> None:
    request = HostJobRequest(
        dag_id="freedom_market_data_daily",
        task_id="sync_income",
        run_id="manual__20260315T123500",
        trade_date="20260315",
        command=["python", "backend/scripts/daily/sync_financial_reports.py", "--dataset", "income", "--start-date", "20260315", "--end-date", "20260315"],
    )

    command = build_host_runner_command(request)

    assert "sync_financial_reports.py" in command
    assert "--dataset income" in command


def test_ssh_connection_config_defaults_to_host_docker_internal() -> None:
    config = SshConnectionConfig.from_env({})

    assert config.host == "host.docker.internal"
    assert config.port == 22
    assert config.username == "james"
    assert config.key_path == "/opt/airflow/ssh/freedom_sync/id_ed25519"


def test_build_host_python_command_uses_explicit_conda_profile_fallback() -> None:
    command = build_host_python_command("print('ok')")

    assert "$HOME/miniconda3/etc/profile.d/conda.sh" in command
    assert "conda activate freedom" in command
