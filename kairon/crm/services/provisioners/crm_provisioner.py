import json
import subprocess
import re
from typing import Dict, Any
from loguru import logger
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.provisioners.base_provisioner import BaseProvisioner
from kairon.crm.services.preflight_validator import PreFlightValidator


class CRMProvisioner(BaseProvisioner):
    """
    Tier 1 Standalone Provisioning Strategy (Pure Frappe + Frappe CRM).
    Provisions lightweight site running only Frappe Framework and Frappe CRM.
    Setup time: ~15s, DB footprint: ~70% lower than ERPNext monolith.
    """

    def provision(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str
    ) -> Dict[str, Any]:
        logger.info(f"[CRMProvisioner] Starting Tier 1 CRM Provisioning for company '{company_name}', bot '{bot}'...")

        doc = CRMClientDetails.objects(company_name__iexact=company_name.strip()).first()
        if not doc:
            raise AppException(f"CRMClientDetails record not found for company: {company_name}")

        clean_name = "".join(c if c.isalnum() else "_" for c in company_name.lower())
        site_name = f"{clean_name}.localhost"
        doc.site_name = site_name

        # Phase 0: Pre-flight validation
        PreFlightValidator.validate_infrastructure(self.container_name, site_name, self.plan, is_upgrade=False)

        # Database name resolution
        base_db_name = f"frappe_crm_{clean_name}"[:63].rstrip('_')
        db_name = base_db_name

        # Execute bench new-site with --install-app crm
        cmd = [
            "docker", "exec", self.container_name,
            "bench", "new-site", site_name,
            "--db-name", db_name,
            "--db-host", self.bench_config.get("db_host", "db"),
            "--db-port", str(self.bench_config.get("db_port", 5432)),
            "--db-type", "postgres",
            "--db-root-username", self.bench_config.get("db_user", "postgres"),
            "--db-root-password", self.bench_config.get("db_password", ""),
            "--admin-password", admin_password,
            "--install-app", "crm",
            "--force"
        ]

        logger.info(f"[CRMProvisioner] Running command: docker exec {self.container_name} bench new-site {site_name} --install-app crm")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise AppException(f"[CRMProvisioner] Bench new-site failed: {res.stderr or res.stdout}")

        # Also install kairon_connector for webhook and lead handling
        connector_cmd = [
            "docker", "exec", self.container_name,
            "bench", "--site", site_name, "install-app", "kairon_connector"
        ]
        logger.info(f"[CRMProvisioner] Installing kairon_connector on {site_name}")
        c_res = subprocess.run(connector_cmd, capture_output=True, text=True)
        if c_res.returncode != 0:
            logger.warning(f"[CRMProvisioner] kairon_connector install failed: {c_res.stderr or c_res.stdout}")

        # Post-creation setup: Encryption key, setup wizard bypass, homepage, migrate & user creation
        self.prelock_encryption_key(site_name)
        self.set_homepage(site_name, self.plan.home_page)
        self.setup_user_and_migrate(site_name, doc.user, admin_password, company_name=company_name)

        # Setup wizard bypass for Frappe & CRM
        try:
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "execute", "frappe.db.set_value",
                "--args", "['Installed Application', {'app_name': 'frappe'}, 'is_setup_complete', 1]"
            ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "execute", "frappe.db.set_single_value",
                "--args", "['System Settings', 'setup_complete', 1]"
            ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "clear-cache"
            ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "use", site_name
            ], capture_output=True)
        except Exception as e:
            logger.warning(f"[CRMProvisioner] Setup wizard bypass warning: {e}")

        # Worker reload
        self.reload_gunicorn_workers()

        # Update metadata in MongoDB
        doc.tier = 1
        doc.installed_apps = self.plan.apps
        doc.onboarding_status = CRMOnboardingStatus.SITE_CREATED.value
        doc.save()

        logger.info(f"[CRMProvisioner] Tier 1 CRM site '{site_name}' provisioned successfully.")
        return {
            "status": "success",
            "tier": 1,
            "site_name": site_name,
            "message": "Tier 1 Standalone CRM site provisioned successfully."
        }
