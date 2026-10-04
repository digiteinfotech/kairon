import subprocess
from datetime import datetime
from typing import Dict, Any
from loguru import logger
from kairon.exceptions import AppException
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.provisioners.base_provisioner import BaseProvisioner
from kairon.crm.services.preflight_validator import PreFlightValidator


class AppUpgradeProvisioner(BaseProvisioner):
    """
    In-Place Upgrade Strategy (Tier 1 ──► Tier 2 Upgrade).
    Executes:
    1. Atomic Mongo lock acquisition (lock:upgrade:<site_name>).
    2. Pre-upgrade database backup (bench backup).
    3. bench --site <site> install-app erpnext.
    4. DB patch repair fallback (bench migrate) on error.
    5. State & tier metadata updates in MongoDB.
    """

    def provision(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str
    ) -> Dict[str, Any]:
        doc = CRMClientDetails.objects(company_name__iexact=company_name.strip()).first()
        if not doc:
            raise AppException(f"CRMClientDetails record not found for company: {company_name}")

        site_name = doc.site_name
        if not site_name:
            raise AppException(f"No existing bench site found to upgrade for company {company_name}")

        # Acquire lock atomically -- the previous read-then-write (`if doc.lock: raise`
        # followed by a separate `doc.save()`) let two concurrent upgrade calls both
        # pass the check and run `bench install-app` against the same site.
        updated_count = CRMClientDetails.objects(
            company_name__iexact=company_name.strip(), lock=False
        ).update_one(
            set__lock=True,
            set__lock_timestamp=datetime.utcnow(),
            set__onboarding_status=CRMOnboardingStatus.UPGRADING_TO_TIER_2.value,
        )
        if updated_count == 0:
            raise AppException(f"Upgrade operation already in progress for site '{site_name}'. Please wait or retry.")
        doc = CRMClientDetails.objects(company_name__iexact=company_name.strip()).first()

        try:
            # Phase 0: Infrastructure & Container Readiness Check
            PreFlightValidator.validate_infrastructure(self.container_name, site_name, self.plan, is_upgrade=True)

            # Step 1: Pre-Upgrade Database Backup
            logger.info(f"[AppUpgradeProvisioner] Step 1: Creating pre-upgrade backup for '{site_name}'...")
            backup_cmd = ["docker", "exec", self.container_name, "bench", "--site", site_name, "backup"]
            backup_res = subprocess.run(backup_cmd, capture_output=True, text=True)
            if backup_res.returncode == 0:
                logger.info(f"[AppUpgradeProvisioner] Backup created successfully: {backup_res.stdout.strip()}")
                doc.latest_backup_path = backup_res.stdout.strip()

            # Step 2: Execute bench install-app erpnext
            logger.info(f"[AppUpgradeProvisioner] Step 2: Upgrading site '{site_name}' by installing 'erpnext'...")
            upgrade_cmd = [
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "install-app", "erpnext"
            ]
            upgrade_res = subprocess.run(upgrade_cmd, capture_output=True, text=True, timeout=300)

            if upgrade_res.returncode != 0:
                logger.error(f"[AppUpgradeProvisioner] Upgrade command failed: {upgrade_res.stderr or upgrade_res.stdout}")
                # Failure Recovery: Run bench migrate to repair partial DB schema
                logger.info("[AppUpgradeProvisioner] Running bench migrate to repair DB schema state...")
                subprocess.run(["docker", "exec", self.container_name, "bench", "--site", site_name, "migrate"], capture_output=True)

                doc.onboarding_status = CRMOnboardingStatus.FAILED_UPGRADE.value
                doc.last_error = upgrade_res.stderr or upgrade_res.stdout
                raise AppException(f"Site upgrade to ERPNext failed: {upgrade_res.stderr or upgrade_res.stdout}")

            # Step 3: Set Tier 2 homepage
            self.set_homepage(site_name, "workspace/CRM")
            self.reload_gunicorn_workers()

            # Step 4: Update metadata in MongoDB
            doc.tier = 2
            if "erpnext" not in doc.installed_apps:
                doc.installed_apps.append("erpnext")
            doc.onboarding_status = CRMOnboardingStatus.COMPLETED.value
            doc.last_error = None
            doc.save()

            logger.info(f"[AppUpgradeProvisioner] Site '{site_name}' upgraded to Tier 2 ERPNext successfully.")
            return {
                "status": "success",
                "tier": 2,
                "site_name": site_name,
                "message": "Site upgraded from Tier 1 Standalone to Tier 2 ERPNext Suite successfully."
            }

        except Exception as e:
            # Guarantee a terminal state on any failure -- including ones that never
            # reach the explicit FAILED_UPGRADE assignment above (e.g. a pre-flight
            # failure or subprocess.TimeoutExpired) -- so the record doesn't stay
            # stuck in the non-terminal UPGRADING_TO_TIER_2 state forever.
            if doc.onboarding_status == CRMOnboardingStatus.UPGRADING_TO_TIER_2.value:
                doc.onboarding_status = CRMOnboardingStatus.FAILED_UPGRADE.value
                doc.last_error = str(e)
            raise

        finally:
            # Release lock
            doc.lock = False
            doc.lock_timestamp = None
            doc.save()
