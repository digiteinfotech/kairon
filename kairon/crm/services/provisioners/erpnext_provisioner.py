import subprocess
from typing import Dict, Any
from loguru import logger
from kairon.exceptions import AppException
from kairon.crm.models import CRMOnboardingStatus
from kairon.crm.services.provisioners.base_provisioner import BaseProvisioner
from kairon.crm.services.preflight_validator import PreFlightValidator


class ERPNextProvisioner(BaseProvisioner):
    """
    Tier 2 Monolithic Provisioning Strategy (Frappe + ERPNext + HRMS).
    Provisions full ERP suite for customers requiring Accounting, Inventory, or HR.
    """

    LABEL = "ERPNextProvisioner"

    def provision(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str
    ) -> Dict[str, Any]:
        logger.info(f"[{self.LABEL}] Starting Tier 2 ERPNext Suite Provisioning for company '{company_name}', bot '{bot}'...")

        doc = self._load_client_doc(company_name)
        clean_name, site_name = self._clean_site_name(company_name)
        doc.site_name = site_name

        # Phase 0: Pre-flight validation
        PreFlightValidator.validate_infrastructure(self.container_name, site_name, self.plan, is_upgrade=False)

        # Database name resolution
        db_name = f"erpnext_{clean_name}"[:63].rstrip('_')

        self._bench_new_site(site_name, db_name, admin_password, "erpnext", self.LABEL)
        self._install_kairon_connector(site_name, self.LABEL)

        # Post-creation setup: Encryption key, homepage
        self.prelock_encryption_key(site_name)
        self.set_homepage(site_name, self.plan.home_page)

        # Install additional Tier 2 apps if requested (e.g. HRMS)
        for app in self.plan.apps:
            if app not in ("frappe", "erpnext"):
                logger.info(f"[{self.LABEL}] Installing additional Tier 2 app '{app}' on {site_name}...")
                install_cmd = [
                    "docker", "exec", self.container_name,
                    "bench", "--site", site_name, "install-app", app
                ]
                res = subprocess.run(install_cmd, capture_output=True, text=True, timeout=600)
                if res.returncode != 0:
                    raise AppException(f"[{self.LABEL}] install-app '{app}' failed: {res.stderr or res.stdout}")

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
            logger.warning(f"[{self.LABEL}] Product isolation setup warning: {iso_err}")

        self._bypass_setup_wizard(site_name, ["frappe", "erpnext"], self.LABEL)

        # Worker reload
        self.reload_gunicorn_workers()

        # Update metadata in MongoDB. NOTE: status is SITE_CREATED here, not COMPLETED --
        # marking it COMPLETED at this point (as this used to) skips every remaining step
        # in ProvisioningService.execute_onboarding_workflow (health check, Company/
        # integration-user/webhook-secret setup, the tenant owner's actual User record +
        # welcome email, and final verification), since each of those steps only runs
        # when the status guard matches its expected prior state. That left every Tier 2
        # (ERPNext) tenant with only "Administrator" and an ephemeral password nobody was
        # ever told -- no real login for the tenant owner at all. Matches CRMProvisioner's
        # (Tier 1) already-correct behavior of stopping at SITE_CREATED.
        doc.tier = 2
        doc.installed_apps = self.plan.apps
        doc.onboarding_status = CRMOnboardingStatus.SITE_CREATED.value
        doc.save()

        logger.info(f"[{self.LABEL}] Tier 2 ERPNext site '{site_name}' provisioned successfully.")
        return {
            "status": "success",
            "tier": 2,
            "site_name": site_name,
            "message": "Tier 2 ERPNext Suite site provisioned successfully."
        }
