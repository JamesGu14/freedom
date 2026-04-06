from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Mapping


DEFAULT_SSH_HOST = "host.docker.internal"
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "james"
DEFAULT_SSH_KEY_PATH = "/opt/airflow/ssh/freedom_sync/id_ed25519"
DEFAULT_PROJECT_ROOT = "/home/james/projects/freedom"
DEFAULT_HOST_WRAPPER_PATH = f"{DEFAULT_PROJECT_ROOT}/scripts/run_freedom_sync_job.sh"


def _conda_activation_snippet() -> str:
    return (
        'if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then '
        'source "$HOME/miniconda3/etc/profile.d/conda.sh"; '
        'elif command -v conda >/dev/null 2>&1; then '
        'source "$(conda info --base)/etc/profile.d/conda.sh"; '
        'else echo "conda init script not found" >&2; exit 127; '
        "fi"
    )


@dataclass(frozen=True)
class HostJobRequest:
    dag_id: str
    task_id: str
    run_id: str
    trade_date: str
    command: list[str]


@dataclass(frozen=True)
class SshConnectionConfig:
    host: str
    port: int
    username: str
    key_path: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SshConnectionConfig":
        source = env if env is not None else os.environ
        return cls(
            host=str(source.get("FREEDOM_SSH_HOST", DEFAULT_SSH_HOST)).strip() or DEFAULT_SSH_HOST,
            port=int(str(source.get("FREEDOM_SSH_PORT", DEFAULT_SSH_PORT)).strip() or DEFAULT_SSH_PORT),
            username=str(source.get("FREEDOM_SSH_USER", DEFAULT_SSH_USER)).strip() or DEFAULT_SSH_USER,
            key_path=str(source.get("FREEDOM_SSH_KEY_PATH", DEFAULT_SSH_KEY_PATH)).strip() or DEFAULT_SSH_KEY_PATH,
        )


def build_host_runner_command(request: HostJobRequest, *, wrapper_path: str = DEFAULT_HOST_WRAPPER_PATH) -> str:
    shell_command = shlex.join(
        [
            "bash",
            wrapper_path,
            "--dag-id",
            request.dag_id,
            "--task-id",
            request.task_id,
            "--run-id",
            request.run_id,
            "--trade-date",
            request.trade_date,
            "--",
            *request.command,
        ]
    )
    return f"bash -lc {shlex.quote(shell_command)}"


def build_host_python_command(python_code: str, *, project_root: str = DEFAULT_PROJECT_ROOT) -> str:
    prefix = (
        _conda_activation_snippet()
        + " && conda activate freedom"
        + f' && export PYTHONPATH="{project_root}/backend${{PYTHONPATH:+:${{PYTHONPATH}}}}"'
        + f" && cd {shlex.quote(project_root)}"
    )
    body = f"python -c {shlex.quote(python_code)}"
    return f"bash -lc {shlex.quote(prefix + ' && ' + body)}"


def run_ssh_command(config: SshConnectionConfig, remote_command: str, *, timeout_seconds: int = 7200) -> tuple[int, str, str]:
    with open(config.key_path, "r", encoding="utf-8") as handle:
        key_text = handle.read()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as temp_key:
        temp_key.write(key_text)
        temp_key.flush()
        os.chmod(temp_key.name, 0o600)
        ssh_command = [
            "ssh",
            "-i",
            temp_key.name,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-p",
            str(config.port),
            f"{config.username}@{config.host}",
            remote_command,
        ]
        result = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    return result.returncode, result.stdout, result.stderr


def run_host_job(request: HostJobRequest, *, config: SshConnectionConfig | None = None, timeout_seconds: int = 7200) -> str:
    resolved = config or SshConnectionConfig.from_env()
    remote_command = build_host_runner_command(request)
    exit_status, stdout, stderr = run_ssh_command(resolved, remote_command, timeout_seconds=timeout_seconds)
    if exit_status != 0:
        raise RuntimeError(f"host job failed: task_id={request.task_id} exit_status={exit_status} stderr={stderr.strip()}")
    return stdout
