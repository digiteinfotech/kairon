import uuid
import time
from loguru import logger
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.crm.services.bench_runner import get_bench_runner
from kairon.crm.services.docker_utils import resolve_container_name, run_docker
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.base_provisioner import BaseProvisioner
from kairon.crm.services.provisioners.factory import ProvisionerFactory


class BenchExecutor:

    def _resolve_container_name(self, bench_config: dict) -> str:
        """
        Resolves the backend container name dynamically from configuration,
        falling back to docker ps resolution if empty.
        """
        return resolve_container_name(bench_config, "BenchExecutor")

    def provision_site(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str = None, selected_features: list = None
    ):
        logger.info(
            f"BenchExecutor.provision_site: company_name={company_name}, abbr={abbr}, "
            f"default_currency={default_currency}, country={country}, features={selected_features}"
        )

        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})

        # Phase 0: Pre-flight Configuration Validation
        plan = PreFlightValidator.validate_configuration(selected_features or ["crm"])

        # Instantiate strategy via ProvisionerFactory
        provisioner = ProvisionerFactory.create(plan, bench_config)

        # Execute provisioning strategy
        return provisioner.provision(
            company_name=company_name,
            abbr=abbr,
            default_currency=default_currency,
            country=country,
            admin_password=admin_password,
            bot=bot or company_name
        )

    def drop_site(self, site_name: str, container_name: str = None, idempotency_key: str = None, runner=None):
        """
        Removes a tenant site and its database (no backup). Raises AppException when the site could not be removed.
        Shared by rollback of a failed provisioning run and by tenant teardown. If `drop-site` cannot run (e.g. the
        database itself is the problem), the site directory is removed so the name can be provisioned again.
        """
        bench_config = Utility.environment.get("crm", {}).get("bench", {})
        runner = runner or get_bench_runner()
        if runner:
            result = runner.run("drop_site", site_name,
                                idempotency_key=idempotency_key or f"{uuid.uuid4().hex}:drop_site:{site_name}")
            if not result.ok:
                raise AppException(f"Could not remove site {site_name}: {result.error}")
            return
        container = container_name or self._resolve_container_name(bench_config)
        drop = run_docker([
            "docker", "exec", container, "bench", "drop-site", site_name, "--force", "--no-backup",
            "--db-root-username", bench_config.get("db_user", "postgres"),
            "--db-root-password", bench_config.get("db_password", ""),
        ], capture_output=True, text=True, timeout=120)
        if drop.returncode == 0:
            logger.info(f"Removed site {site_name}.")
            return
        removed = run_docker(["docker", "exec", container, "rm", "-rf", f"sites/{site_name}"],
                                 capture_output=True, text=True, timeout=60)
        if removed.returncode != 0:
            raise AppException(f"Could not remove site {site_name}.")
        logger.warning(f"drop-site failed; removed directory sites/{site_name}. Its database may need manual cleanup.")

    def set_admin_password(self, site_name: str, admin_password: str):
        """
        Securely rotates/sets the Administrator password of an existing site
        without storing it persistently.
        """
        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        from kairon.crm.services.bench_runner import get_bench_runner
        runner = get_bench_runner()
        if runner:
            result = runner.run("set_admin_password", site_name, secrets={"admin_password": admin_password},
                                idempotency_key=f"{uuid.uuid4().hex}:set_admin_password:{site_name}")
            if not result.ok:
                raise AppException(f"Failed to set admin password on retry: {result.error}")
            return
        container_name = self._resolve_container_name(bench_config)

        cmd = [
            "docker", "exec", container_name,
            "bench", "--site", site_name, "set-admin-password", admin_password
        ]
        logger.info(f"Running command: docker exec {container_name} bench --site {site_name} set-admin-password ********")
        result = run_docker(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            output = BaseProvisioner._scrub(result.stderr or result.stdout, admin_password)    # the command line carried the password
            raise AppException(f"Failed to set admin password on retry: {output}")

    def reload_gunicorn_workers(self, container_name: str):
        """
        Sends SIGHUP to Gunicorn master (PID 1) inside container to gracefully reload all worker processes.
        This ensures preloaded Gunicorn workers reload newly created site configs and encryption keys.
        """
        try:
            cmd = [
                "docker", "exec", container_name,
                "/home/frappe/frappe-bench/env/bin/python", "-c",
                "import os, signal; os.kill(1, signal.SIGHUP)"
            ]
            run_docker(cmd, capture_output=True, timeout=10)
            time.sleep(2)
            logger.info(f"Triggered Gunicorn worker reload (SIGHUP) in {container_name}")
        except Exception as e:
            logger.warning(f"Failed to reload Gunicorn workers: {e}")
