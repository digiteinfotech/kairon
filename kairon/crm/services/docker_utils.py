import re
import shutil
import subprocess  # nosec B404 - the one module that starts processes; arguments are always lists, never shell strings
from typing import List
from loguru import logger

from kairon.exceptions import AppException


PIPE = subprocess.PIPE
TimeoutExpired = subprocess.TimeoutExpired      # re-exported so callers need not import subprocess themselves
CompletedProcess = subprocess.CompletedProcess


def run_docker(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """
    The one place a `docker ...` command line is executed. `cmd` is always an argument list (never a shell string), its
    values are validated by the callers (container names by `resolve_container_name`, site names by `SITE_PATTERN`, app
    names by the provisioning matrix) and secrets travel as arguments exactly as `docker exec` requires. The binary is
    resolved to its absolute path here, so no call site starts a process from a partial executable path.
    """
    args = _docker_args(cmd)
    return subprocess.run(args, **_with_binary(args, kwargs))  # nosec B603 - literal program name, argument list, validated inputs


def popen_docker(cmd: List[str], **kwargs) -> subprocess.Popen:
    """`run_docker` for piped processes (the frontend asset sync)."""
    args = _docker_args(cmd)
    return subprocess.Popen(args, **_with_binary(args, kwargs))  # nosec B603 - literal program name, argument list, validated inputs


def _docker_args(cmd: List[str]) -> List[str]:
    """
    The program is always the literal `docker`, never a value that came from a caller; everything after it is plain data passed
    as separate arguments (no shell). Anything that is not a `docker ...` list of strings is refused.
    """
    if not cmd or cmd[0] != "docker" or not all(isinstance(arg, str) and "\x00" not in arg for arg in cmd):
        raise AppException("Only docker commands can be run here.")
    return ["docker", *cmd[1:]]


def _with_binary(cmd: List[str], kwargs: dict) -> dict:
    """Adds the resolved absolute path of `docker` (argv[0] stays "docker"); nothing is added when it is not installed."""
    binary = shutil.which("docker") if cmd and cmd[0] == "docker" else None
    return {**kwargs, "executable": binary} if binary else kwargs


CONTAINER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def resolve_container_name(bench_config: dict, log_prefix: str = "DockerUtils") -> str:
    """
    Resolves the backend Frappe/ERPNext container name from config,
    falling back to a docker ps label lookup, then a hardcoded default.
    """
    from kairon.crm.services.bench_runner import execution_mode
    if execution_mode() != "docker":
        return ""   # runner mode has no container, even if one is configured (and may have no docker binary at all)
    container_name = bench_config.get("container_name")
    if not container_name:
        cmd = [
            "docker", "ps",
            "--filter", "label=com.docker.compose.service=backend",
            "--filter", "label=com.docker.compose.project=frappe",
            "--format", "{{.Names}}"
        ]
        res = run_docker(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            container_name = res.stdout.strip()
            logger.info(f"[{log_prefix}] Dynamically resolved container name: {container_name}")
        else:
            container_name = "frappe-backend-1"
            logger.warning(f"[{log_prefix}] Failed to resolve container name. Using fallback: {container_name}")
    if container_name and not CONTAINER_NAME_PATTERN.match(container_name):
        raise AppException("The configured Bench container name is not a valid Docker container name.")
    return container_name
