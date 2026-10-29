import subprocess
from datetime import datetime, timedelta
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
    5. Tier metadata update in MongoDB, leaving the tenant at SITE_CREATED.

    The upgrade installs the app only. It never marks the tenant COMPLETED: the Tier 2 Company, the tenant owner's
    roles/company permission and the final verification are done by the normal ProvisioningService phases, which resume
    from SITE_CREATED exactly as they do after a fresh Tier 2 provision (same rule as ERPNextProvisioner). COMPLETED is
    reached only when those phases succeed.
    """

    LOCK_STALE_AFTER = timedelta(hours=2)

    def provision(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str
    ) -> Dict[str, Any]:
        doc = self._load_client_doc(company_name, bot)

        site_name = doc.site_name
        if not site_name:
            raise AppException(f"No existing bench site found to upgrade for company {company_name}")

        # A repeated request must not touch a tenant that is already Tier 2 (it could be COMPLETED or mid-provisioning).
        if doc.tier == 2 and "erpnext" in (doc.installed_apps or []):
            logger.info(f"[AppUpgradeProvisioner] '{site_name}' is already Tier 2; nothing to do.")
            return {"status": "already_upgraded", "tier": 2, "site_name": site_name,
                    "message": "Site is already on Tier 2 ERPNext Suite."}

        # Acquire lock atomically -- the previous read-then-write (`if doc.lock: raise`
        # followed by a separate `doc.save()`) let two concurrent upgrade calls both
        # pass the check and run `bench install-app` against the same site.
        from mongoengine.queryset.visitor import Q
        updated_count = CRMClientDetails.objects(
            Q(bot=bot) & Q(company_name__iexact=company_name.strip())
            & (Q(lock=False) | Q(lock_timestamp__lt=datetime.utcnow() - self.LOCK_STALE_AFTER))   # crashed run recovery
        ).update_one(
            set__lock=True,
            set__lock_timestamp=datetime.utcnow(),
            set__onboarding_status=CRMOnboardingStatus.UPGRADING_TO_TIER_2.value,
        )
        if updated_count == 0:
            raise AppException(f"Upgrade operation already in progress for site '{site_name}'. Please wait or retry.")
        doc = self._load_client_doc(company_name, bot)

        try:
            if self.runner:
                raise AppException("Tier 1 -> Tier 2 upgrades are not supported in BENCH_EXECUTION_MODE=runner yet.")
            # Phase 0: Infrastructure & Container Readiness Check
            PreFlightValidator.validate_infrastructure(self.container_name, site_name, self.plan, is_upgrade=True)

            # Step 1: Pre-Upgrade Database Backup (an upgrade is never started without a restore point)
            self._backup_before_upgrade(doc, site_name)

            # Step 2: Execute bench install-app erpnext
            logger.info(f"[AppUpgradeProvisioner] Step 2: Upgrading site '{site_name}' by installing 'erpnext'...")
            upgrade_cmd = [
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "install-app", "erpnext"
            ]
            # A previous attempt may have installed the app and died before recording it; installing twice would fail.
            if self._erpnext_installed(site_name):
                logger.info(f"[AppUpgradeProvisioner] 'erpnext' is already installed on '{site_name}'; skipping install-app.")
                upgrade_res = subprocess.CompletedProcess(upgrade_cmd, 0, "", "")
            else:
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

            # Step 4: Record the new tier. Not COMPLETED: the Tier 2 Company / owner roles / verification still have to run.
            doc.tier = 2
            if "erpnext" not in (doc.installed_apps or []):
                doc.installed_apps = list(doc.installed_apps or []) + ["erpnext"]
            doc.onboarding_status = CRMOnboardingStatus.SITE_CREATED.value
            doc.last_error = None
            doc.save()

            logger.info(f"[AppUpgradeProvisioner] ERPNext installed on '{site_name}'; Tier 2 setup phases still pending.")
            return {
                "status": "success",
                "tier": 2,
                "site_name": site_name,
                "message": "ERPNext installed. Tier 2 setup (company, owner roles, verification) continues via onboarding."
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

    def _erpnext_installed(self, site_name: str) -> bool:
        """True when `bench list-apps` for the site already shows erpnext. Any doubt answers False (install is attempted)."""
        try:
            res = subprocess.run(["docker", "exec", self.container_name, "bench", "--site", site_name, "list-apps"],
                                 capture_output=True, text=True, timeout=60)
        except Exception:
            return False
        out = res.stdout if isinstance(res.stdout, str) else (res.stdout or b"").decode("utf-8", "ignore")
        return res.returncode == 0 and any(line.split()[:1] == ["erpnext"] for line in out.splitlines())

    def _backup_before_upgrade(self, doc, site_name: str):
        logger.info(f"[AppUpgradeProvisioner] Step 1: Creating pre-upgrade backup for '{site_name}'...")
        backup_res = subprocess.run(["docker", "exec", self.container_name, "bench", "--site", site_name, "backup"],
                                    capture_output=True, text=True)
        if backup_res.returncode != 0:
            # install-app changes the schema and cannot be undone.
            doc.onboarding_status = CRMOnboardingStatus.FAILED_UPGRADE.value
            doc.last_error = "Pre-upgrade backup failed; upgrade not started."
            raise AppException(doc.last_error)
        logger.info(f"[AppUpgradeProvisioner] Backup created successfully: {backup_res.stdout.strip()}")
        doc.latest_backup_path = backup_res.stdout.strip()
