import subprocess
from loguru import logger


def resolve_container_name(bench_config: dict, log_prefix: str = "DockerUtils") -> str:
    """
    Resolves the backend Frappe/ERPNext container name from config,
    falling back to a docker ps label lookup, then a hardcoded default.
    """
    container_name = bench_config.get("container_name")
    if not container_name:
        cmd = [
            "docker", "ps",
            "--filter", "label=com.docker.compose.service=backend",
            "--filter", "label=com.docker.compose.project=frappe",
            "--format", "{{.Names}}"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            container_name = res.stdout.strip()
            logger.info(f"[{log_prefix}] Dynamically resolved container name: {container_name}")
        else:
            container_name = "frappe-backend-1"
            logger.warning(f"[{log_prefix}] Failed to resolve container name. Using fallback: {container_name}")
    return container_name
