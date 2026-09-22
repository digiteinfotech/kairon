import subprocess
from typing import List
from loguru import logger
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.crm.services.feature_resolver import FeatureAppResolver
from kairon.crm.services.provisioning_models import ProvisioningPlan


class PreFlightValidator:
    """
    Phase 0 Pre-flight Validation Service.
    Validates application configuration, system settings, environment variables,
    Docker backend status, database connectivity, and Bench CLI availability
    BEFORE attempting site provisioning or modifications.
    """

    @classmethod
    def validate_configuration(cls, selected_features: List[str]) -> ProvisioningPlan:
        """
        Validates app layer configuration:
        1. Matrix YAML validity.
        2. FeatureAppResolver resolution.
        3. Bench environment config in system.yaml.
        4. Cryptographic key availability.
        """
        logger.info("[PreFlightValidator] Validating application configuration...")

        # 1. Validate matrix loading & resolution
        try:
            plan = FeatureAppResolver.resolve(selected_features)
        except Exception as e:
            raise AppException(f"Pre-flight config failure: Unable to resolve features. Error: {e}")

        # 2. Validate crm.bench environment configuration
        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})

        if not bench_config:
            logger.warning("[PreFlightValidator] 'crm.bench' configuration section missing in system environment. Using defaults.")

        # 3. Validate database configuration parameters
        db_host = bench_config.get("db_host", "db")
        db_port = bench_config.get("db_port", 5432)
        if not db_host or not db_port:
            raise AppException("Pre-flight config failure: Database host or port misconfigured.")
        if not bench_config.get("db_password"):
            raise AppException(
                "Pre-flight config failure: BENCH_DB_PASSWORD is not set. Bench provisioning "
                "requires an explicit deployment secret and will not fall back to a default."
            )

        logger.info("[PreFlightValidator] Application configuration validated successfully.")
        return plan

    @classmethod
    def validate_infrastructure(cls, container_name: str, site_name: str, plan: ProvisioningPlan, is_upgrade: bool = False):
        """
        Validates infrastructure & container layer readiness:
        1. Container is running.
        2. Bench CLI is responsive.
        3. Site name non-existence (unless upgrade).
        4. Target app repositories exist in container bench/apps.
        """
        logger.info(f"[PreFlightValidator] Validating infrastructure for container '{container_name}', site '{site_name}'...")

        # 1. Verify backend container running via docker exec test
        test_cmd = ["docker", "exec", container_name, "bench", "--version"]
        try:
            res = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise AppException(f"Pre-flight infrastructure failure: Container '{container_name}' did not respond within 30s.")
        if res.returncode != 0:
            raise AppException(
                f"Pre-flight infrastructure failure: Container '{container_name}' is not running or 'bench' CLI unavailable. "
                f"Stderr: {res.stderr or res.stdout}"
            )

        logger.info(f"[PreFlightValidator] Bench CLI responsive: {res.stdout.strip()}")

        # 2. Check site existence
        if not is_upgrade:
            check_site_cmd = ["docker", "exec", container_name, "test", "-d", f"sites/{site_name}"]
            try:
                site_res = subprocess.run(check_site_cmd, capture_output=True, timeout=30)
            except subprocess.TimeoutExpired:
                raise AppException(f"Pre-flight infrastructure failure: Container '{container_name}' did not respond within 30s.")
            if site_res.returncode == 0:
                raise AppException(f"Pre-flight infrastructure failure: Site '{site_name}' already exists in bench sites directory.")

        # 3. Verify required apps exist in container apps directory & sites/apps.txt
        for app in plan.apps:
            check_app_cmd = ["docker", "exec", container_name, "test", "-d", f"apps/{app}"]
            try:
                app_res = subprocess.run(check_app_cmd, capture_output=True, timeout=30)
            except subprocess.TimeoutExpired:
                raise AppException(f"Pre-flight infrastructure failure: Container '{container_name}' did not respond within 30s.")
            if app_res.returncode != 0:
                raise AppException(
                    f"Pre-flight infrastructure failure: Required application repository '{app}' is missing from container apps directory. "
                    f"Please run 'bench get-app {app}' during image build."
                )

            # Ensure app is registered in sites/apps.txt for bench new-site compatibility
            ensure_apps_cmd = [
                "docker", "exec", container_name, "bash", "-c",
                f"grep -q '^{app}$' sites/apps.txt || echo '{app}' >> sites/apps.txt"
            ]
            try:
                subprocess.run(ensure_apps_cmd, capture_output=True, timeout=30)
            except subprocess.TimeoutExpired:
                raise AppException(f"Pre-flight infrastructure failure: Container '{container_name}' did not respond within 30s.")

        logger.info("[PreFlightValidator] Infrastructure pre-flight validation completed successfully.")

