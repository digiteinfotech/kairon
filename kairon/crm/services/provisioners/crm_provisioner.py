from typing import Dict, Any
from loguru import logger
from kairon.crm.models import CRMOnboardingStatus
from kairon.crm.services.provisioners.base_provisioner import BaseProvisioner
from kairon.crm.services.preflight_validator import PreFlightValidator


class CRMProvisioner(BaseProvisioner):
    """
    Tier 1 Standalone Provisioning Strategy (Pure Frappe + Frappe CRM).
    Provisions lightweight site running only Frappe Framework and Frappe CRM.
    Setup time: ~15s, DB footprint: ~70% lower than ERPNext monolith.
    """

    LABEL = "CRMProvisioner"

    def provision(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str
    ) -> Dict[str, Any]:
        logger.info(f"[{self.LABEL}] Starting Tier 1 CRM Provisioning for company '{company_name}', bot '{bot}'...")

        doc = self._load_client_doc(company_name)
        clean_name, site_name = self._clean_site_name(company_name)
        doc.site_name = site_name

        # Phase 0: Pre-flight validation
        PreFlightValidator.validate_infrastructure(self.container_name, site_name, self.plan, is_upgrade=False)

        # Database name resolution
        db_name = f"frappe_crm_{clean_name}"[:63].rstrip('_')

        self._bench_new_site(site_name, db_name, admin_password, "crm", self.LABEL)
        self._install_kairon_connector(site_name, self.LABEL)

        # Post-creation setup: Encryption key, setup wizard bypass, homepage, migrate & user creation
        self.prelock_encryption_key(site_name)
        self.set_homepage(site_name, self.plan.home_page)
        self.setup_user_and_migrate(site_name, doc.user, admin_password, company_name=company_name)
        self._bypass_setup_wizard(site_name, ["frappe"], self.LABEL)

        # Worker reload
        self.reload_gunicorn_workers()

        # Update metadata in MongoDB
        doc.tier = 1
        doc.installed_apps = self.plan.apps
        doc.onboarding_status = CRMOnboardingStatus.SITE_CREATED.value
        doc.save()

        logger.info(f"[{self.LABEL}] Tier 1 CRM site '{site_name}' provisioned successfully.")
        return {
            "status": "success",
            "tier": 1,
            "site_name": site_name,
            "message": "Tier 1 Standalone CRM site provisioned successfully."
        }
