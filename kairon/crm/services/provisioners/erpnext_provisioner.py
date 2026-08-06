import subprocess
from typing import Dict, Any
from loguru import logger
from kairon.exceptions import AppException
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.provisioners.base_provisioner import BaseProvisioner
from kairon.crm.services.preflight_validator import PreFlightValidator


class ERPNextProvisioner(BaseProvisioner):
    """
    Tier 2 Monolithic Provisioning Strategy (Frappe + ERPNext + HRMS).
    Provisions full ERP suite for customers requiring Accounting, Inventory, or HR.
    """

    def provision(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str
    ) -> Dict[str, Any]:
        logger.info(f"[ERPNextProvisioner] Starting Tier 2 ERPNext Suite Provisioning for company '{company_name}', bot '{bot}'...")

        doc = CRMClientDetails.objects(company_name__iexact=company_name.strip()).first()
        if not doc:
            raise AppException(f"CRMClientDetails record not found for company: {company_name}")

        clean_name = "".join(c if c.isalnum() else "_" for c in company_name.lower())
        site_name = f"{clean_name}.localhost"
        doc.site_name = site_name

        # Phase 0: Pre-flight validation
        PreFlightValidator.validate_infrastructure(self.container_name, site_name, self.plan, is_upgrade=False)

        # Database name resolution
        db_name = f"erpnext_{clean_name}"[:63].rstrip('_')

        # Execute bench new-site with --install-app erpnext
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
            "--install-app", "erpnext",
            "--force"
        ]

        logger.info(f"[ERPNextProvisioner] Running command: docker exec {self.container_name} bench new-site {site_name} --install-app erpnext")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise AppException(f"[ERPNextProvisioner] Bench new-site failed: {res.stderr or res.stdout}")

        # Always install kairon_connector for webhook integration
        connector_cmd = [
            "docker", "exec", self.container_name,
            "bench", "--site", site_name, "install-app", "kairon_connector"
        ]
        logger.info(f"[ERPNextProvisioner] Installing kairon_connector on {site_name}")
        c_res = subprocess.run(connector_cmd, capture_output=True, text=True)
        if c_res.returncode != 0:
            logger.warning(f"[ERPNextProvisioner] kairon_connector install failed: {c_res.stderr or c_res.stdout}")

        # Post-creation setup: Encryption key, homepage
        self.prelock_encryption_key(site_name)
        self.set_homepage(site_name, self.plan.home_page)

        # Install additional Tier 2 apps if requested (e.g. HRMS)
        for app in self.plan.apps:
            if app not in ("frappe", "erpnext"):
                logger.info(f"[ERPNextProvisioner] Installing additional Tier 2 app '{app}' on {site_name}...")
                install_cmd = [
                    "docker", "exec", self.container_name,
                    "bench", "--site", site_name, "install-app", app
                ]
                subprocess.run(install_cmd, capture_output=True)

        # Setup user, roles, password, company, fiscal year, and migrate
        user_email = doc.user if doc.user else "Administrator"
        self.setup_user_and_migrate(
            site_name, user_email, admin_password,
            company_name=company_name, abbr=abbr,
            default_currency=default_currency, country=country
        )




        # Apply Product Isolation Service & Role Profile
        try:
            from kairon.crm.services.erpnext_client import ERPNextClient
            from kairon.crm.services.isolation_service import ProductIsolationService

            base_url = self.bench_config.get("base_url", "http://localhost:8080")
            client = ERPNextClient(base_url, site_name)
            client.login(admin_password)

            selected_features = getattr(self.plan, "selected_features", doc.selected_modules if hasattr(doc, "selected_modules") else ["pos"])
            isolation_info = ProductIsolationService.apply_isolation(client, company_name, selected_features)


            if user_email and user_email.lower() != "administrator":
                client.assign_roles_and_company(
                    user_email,
                    self.plan.default_roles,
                    company_name,
                    module_profile=isolation_info.get("module_profile"),
                    role_profile=isolation_info.get("role_profile"),
                    default_workspace=isolation_info.get("default_workspace", "Point of Sale")
                )
        except Exception as iso_err:
            logger.warning(f"[ERPNextProvisioner] Product isolation setup warning: {iso_err}")

        # Bypass setup wizard
        try:
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "execute", "frappe.db.set_value",
                "--args", "['Installed Application', {'app_name': 'frappe'}, 'is_setup_complete', 1]"
            ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "execute", "frappe.db.set_value",
                "--args", "['Installed Application', {'app_name': 'erpnext'}, 'is_setup_complete', 1]"
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
            logger.warning(f"[ERPNextProvisioner] Setup wizard bypass warning: {e}")

        # Worker reload
        self.reload_gunicorn_workers()

        # Update metadata in MongoDB
        doc.tier = 2
        doc.installed_apps = self.plan.apps
        doc.onboarding_status = CRMOnboardingStatus.COMPLETED.value
        doc.save()

        logger.info(f"[ERPNextProvisioner] Tier 2 ERPNext site '{site_name}' provisioned successfully.")
        return {
            "status": "success",
            "tier": 2,
            "site_name": site_name,
            "message": "Tier 2 ERPNext Suite site provisioned successfully."
        }

