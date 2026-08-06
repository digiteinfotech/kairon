import time
import secrets
import string
from datetime import datetime
from loguru import logger
from pydantic import BaseModel

from kairon.exceptions import AppException
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.bench_executor import BenchExecutor
from kairon.crm.services.erpnext_client import ERPNextClient
from kairon.crm.services.provision_verifier import ProvisionVerifier
from kairon.crm.constants import BUSINESS_MODULE_CATALOG
from kairon.shared.utils import Utility


class ProvisioningResult(BaseModel):
    status: str
    site_name: str = None
    site_url: str = None
    company: str = None
    erpnext_user: str = None
    authentication_method: str = None
    temporary_password: str = None
    error: str = None


class ProvisioningService:
    """
    Workflow orchestrator for ERPNext user provisioning.
    Encapsulates long-running background tasks.
    """

    ALLOWED_TRANSITIONS = {
        CRMOnboardingStatus.PENDING.value: [CRMOnboardingStatus.PROJECT_CREATED.value, CRMOnboardingStatus.FAILED_PROJECT.value],
        CRMOnboardingStatus.PROJECT_CREATED.value: [CRMOnboardingStatus.BENCH_RUNNING.value, CRMOnboardingStatus.FAILED_BENCH.value],
        CRMOnboardingStatus.BENCH_RUNNING.value: [CRMOnboardingStatus.SITE_CREATED.value, CRMOnboardingStatus.FAILED_BENCH.value],
        CRMOnboardingStatus.SITE_CREATED.value: [CRMOnboardingStatus.SITE_HEALTHY.value, CRMOnboardingStatus.FAILED_HEALTH.value],
        CRMOnboardingStatus.SITE_HEALTHY.value: [CRMOnboardingStatus.COMPANY_CREATED.value, CRMOnboardingStatus.FAILED_COMPANY.value],
        CRMOnboardingStatus.COMPANY_CREATED.value: [CRMOnboardingStatus.USER_CREATED.value, CRMOnboardingStatus.FAILED_USER.value],
        CRMOnboardingStatus.USER_CREATED.value: [CRMOnboardingStatus.COMPLETED.value, CRMOnboardingStatus.FAILED_VERIFICATION.value],
    }

    # Retryable failure states mapping to their next success state to allow resumption
    RETRYABLE_STATES = {
        CRMOnboardingStatus.FAILED_BENCH.value: CRMOnboardingStatus.SITE_CREATED.value,
        CRMOnboardingStatus.FAILED_HEALTH.value: CRMOnboardingStatus.SITE_HEALTHY.value,
        CRMOnboardingStatus.FAILED_COMPANY.value: CRMOnboardingStatus.COMPANY_CREATED.value,
        CRMOnboardingStatus.FAILED_USER.value: CRMOnboardingStatus.USER_CREATED.value,
        CRMOnboardingStatus.FAILED_VERIFICATION.value: CRMOnboardingStatus.COMPLETED.value,
    }

    def __init__(self, bot: str, company_name: str, provisioning_id: str):
        self.bot = bot
        self.company_name = company_name
        self.provisioning_id = provisioning_id

    def update_onboarding_status(self, new_status: CRMOnboardingStatus, error_message: str = None):
        """
        Validates and updates the state of the provisioning workflow.
        Ensures strict state machine transitions.
        """
        doc = CRMClientDetails.objects(bot=self.bot, company_name=self.company_name).first()
        if not doc:
            raise AppException("CRMClientDetails not found for status update.")

        current_status = doc.onboarding_status

        # State machine validation
        is_valid = False
        if current_status in self.ALLOWED_TRANSITIONS and new_status.value in self.ALLOWED_TRANSITIONS[current_status]:
            is_valid = True
        elif current_status in self.RETRYABLE_STATES and new_status.value == self.RETRYABLE_STATES[current_status]:
            is_valid = True
        # Allow retry transitions from failed states to their corresponding running/retrying state
        elif current_status == CRMOnboardingStatus.FAILED_BENCH.value and new_status == CRMOnboardingStatus.BENCH_RUNNING:
            is_valid = True

        if not is_valid:
            logger.error(f"[{self.provisioning_id}] Invalid state transition: {current_status} -> {new_status.value}. Preserving existing state.")
            return

        doc.onboarding_status = new_status.value

        if "FAILED" in new_status.value:
            doc.last_error = error_message

        if new_status == CRMOnboardingStatus.COMPLETED or "FAILED" in new_status.value:
            doc.lock = False  # Release lock on terminal states
            doc.workflow_completed_at = datetime.utcnow()

        doc.save()
        logger.info(f"[{self.provisioning_id}] Status updated: {current_status} -> {new_status.value}")

    def execute_onboarding_workflow(self, current_user_email: str, first_name: str, last_name: str) -> ProvisioningResult:
        """
        Executes the resumable onboarding workflow.
        """
        doc = CRMClientDetails.objects(bot=self.bot, company_name=self.company_name).first()
        if not doc:
            return ProvisioningResult(status="FAILED", error="CRM record not found.")

        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        smtp_enabled = bench_config.get("smtp_enabled", False)

        admin_password = None
        temp_password = None
        auth_method = "send_welcome_email" if smtp_enabled else "temporary_password"

        # 1. State: PENDING -> PROJECT_CREATED (instant setup of site_name)
        if doc.onboarding_status == CRMOnboardingStatus.PENDING.value:
            clean_name = "".join(c if c.isalnum() else "_" for c in doc.company_name.lower())
            doc.site_name = f"{clean_name}.localhost"
            doc.save()
            self.update_onboarding_status(CRMOnboardingStatus.PROJECT_CREATED)
            doc = CRMClientDetails.objects(bot=self.bot, company_name=self.company_name).first()

        # 2. Bench Execution (Infrastructure Setup)
        try:
            if doc.onboarding_status in (CRMOnboardingStatus.PROJECT_CREATED.value, CRMOnboardingStatus.FAILED_BENCH.value):
                self.update_onboarding_status(CRMOnboardingStatus.BENCH_RUNNING)

                # Generate admin password in-memory
                admin_password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

                logger.info(f"[{self.provisioning_id}] Starting BenchExecutor...")
                BenchExecutor().provision_site(
                    company_name=doc.company_name,
                    abbr=doc.abbr,
                    default_currency=doc.default_currency,
                    country=doc.country,
                    admin_password=admin_password,
                    bot=self.bot,
                    selected_features=doc.selected_modules
                )

                # Fetch updated doc
                doc = CRMClientDetails.objects(bot=self.bot, company_name=self.company_name).first()
                self.update_onboarding_status(CRMOnboardingStatus.SITE_CREATED)
        except Exception as e:
            logger.error(f"[{self.provisioning_id}] Bench execution failed: {str(e)}")
            self.update_onboarding_status(CRMOnboardingStatus.FAILED_BENCH, str(e))
            return ProvisioningResult(status=CRMOnboardingStatus.FAILED_BENCH.value, error=str(e))

        # Setup Clients
        base_url = bench_config.get("base_url", "http://localhost:80")
        host_header = doc.site_name

        verifier = ProvisionVerifier(base_url, host_header)
        client = ERPNextClient(base_url, host_header)

        # Ensure we have a valid admin_password in memory (rotate it on retry/resumption)
        if not admin_password:
            admin_password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
            logger.info(f"[{self.provisioning_id}] Rotating Administrator password on existing site for login...")
            BenchExecutor().set_admin_password(doc.site_name, admin_password)

        # 3. Wait for Health
        try:
            if doc.onboarding_status in (CRMOnboardingStatus.SITE_CREATED.value, CRMOnboardingStatus.FAILED_HEALTH.value):
                logger.info(f"[{self.provisioning_id}] Waiting for ERPNext health...")
                is_healthy = False
                for _ in range(12): # Wait up to 2 mins
                    if verifier.verify_health():
                        is_healthy = True
                        break
                    time.sleep(10)

                if not is_healthy:
                    raise AppException("ERPNext health check timeout.")

                self.update_onboarding_status(CRMOnboardingStatus.SITE_HEALTHY)
                doc = CRMClientDetails.objects(bot=self.bot, company_name=self.company_name).first()
        except Exception as e:
            logger.error(f"[{self.provisioning_id}] Health check failed: {str(e)}")
            self.update_onboarding_status(CRMOnboardingStatus.FAILED_HEALTH, str(e))
            return ProvisioningResult(status=CRMOnboardingStatus.FAILED_HEALTH.value, error=str(e))

        # 4. Create Company + Integration Infrastructure + Module Configuration
        try:
            if doc.onboarding_status in (CRMOnboardingStatus.SITE_HEALTHY.value, CRMOnboardingStatus.FAILED_COMPANY.value):
                logger.info(f"[{self.provisioning_id}] Logging into ERPNext...")
                client.login(admin_password)

                logger.info(f"[{self.provisioning_id}] Creating Company...")
                client.create_company(doc.company_name, doc.abbr, doc.default_currency, doc.country)

                logger.info(f"[{self.provisioning_id}] Ensuring default SMTP Email Account...")
                client.ensure_default_smtp_account()

                clean_site_domain = doc.site_name.replace("_", "-")
                integration_email = f"kairon-crm@{clean_site_domain}"
                logger.info(f"[{self.provisioning_id}] Creating integration user {integration_email}...")
                client.create_integration_user(integration_email)

                # 4c: Generate and store API keys for the integration user
                logger.info(f"[{self.provisioning_id}] Generating API keys for integration user...")
                keys = client.generate_keys_for_user(integration_email)
                doc.kairon_integration_user = integration_email
                doc.kairon_api_key = Utility.encrypt_message(keys["api_key"])
                doc.kairon_api_secret = Utility.encrypt_message(keys["api_secret"])
                doc.save()

                # Authenticate client with token for integration permission check & module ops
                client.authenticate_with_token(keys["api_key"], keys["api_secret"])

                # 4e: Fail-fast Integration Permission Check
                logger.info(f"[{self.provisioning_id}] Validating integration user permissions...")
                if not client.validate_integration_permissions():
                    raise AppException("Integration user permission validation failed. Aborting provisioning.")

                # 4d: Idempotently create the User Invitation webhook in ERPNext
                import secrets as secrets_mod
                webhook_secret = secrets_mod.token_hex(32)
                kairon_base_url = crm_config.get("server_url") or Utility.environment.get("app", {}).get("server_url", "")
                logger.info(f"[{self.provisioning_id}] Ensuring invitation webhook at {kairon_base_url}...")
                client.ensure_invitation_webhook(
                    kairon_url=kairon_base_url,
                    site_name=doc.site_name,
                    webhook_secret=webhook_secret
                )
                doc.webhook_secret = Utility.encrypt_message(webhook_secret)

                # 4f & 4g: Module & Product Isolation Engine Setup
                from kairon.crm.services.feature_resolver import FeatureAppResolver
                from kairon.crm.services.isolation_service import ProductIsolationService
                plan = FeatureAppResolver.resolve(doc.selected_modules)
                matrix = FeatureAppResolver.load_matrix()

                selected_mods = doc.selected_modules
                if not selected_mods:
                    selected_mods = list(BUSINESS_MODULE_CATALOG.keys())
                    doc.selected_modules = selected_mods

                logger.info(f"[{self.provisioning_id}] Applying ProductIsolationService for selection: {selected_mods}")
                isolation_info = ProductIsolationService.apply_isolation(client, doc.company_name, selected_mods)
                doc.module_profile_name = isolation_info["module_profile"]
                target_role_profile = isolation_info["role_profile"]

                doc.save()


                self.update_onboarding_status(CRMOnboardingStatus.COMPANY_CREATED)
                doc = CRMClientDetails.objects(bot=self.bot, company_name=self.company_name).first()
        except Exception as e:
            logger.error(f"[{self.provisioning_id}] Company creation / module configuration failed: {str(e)}")
            self.update_onboarding_status(CRMOnboardingStatus.FAILED_COMPANY, str(e))
            return ProvisioningResult(status=CRMOnboardingStatus.FAILED_COMPANY.value, error=str(e))

        # 5. Create User & Assign Roles & Module Profile
        try:
            if doc.onboarding_status in (CRMOnboardingStatus.COMPANY_CREATED.value, CRMOnboardingStatus.FAILED_USER.value):
                logger.info(f"[{self.provisioning_id}] Logging into ERPNext...")
                client.login(admin_password)

                logger.info(f"[{self.provisioning_id}] Creating ERPNext User...")
                if not smtp_enabled:
                    temp_password = "Password@123"

                client.create_erpnext_user(
                    email=current_user_email,
                    first_name=first_name,
                    last_name=last_name,
                    send_welcome_email=smtp_enabled,
                    password=temp_password
                )

                logger.info(f"[{self.provisioning_id}] Assigning Roles, Company & Module Profile '{doc.module_profile_name}'...")
                roles = plan.default_roles or ["System Manager", "Sales Manager"]
                target_default_ws = catalog[selected_mods[0]]["workspace"] if (selected_mods and selected_mods[0] in catalog) else "CRM"
                
                # Check matrix for explicit home_page workspace override
                for mod_key in selected_mods:
                    if mod_key in matrix and "home_page" in matrix[mod_key]:
                        hp = matrix[mod_key]["home_page"]
                        if hp.startswith("workspace/"):
                            target_default_ws = hp.replace("workspace/", "")
                        break

                client.assign_roles_and_company(
                    current_user_email,
                    roles,
                    doc.company_name,
                    module_profile=doc.module_profile_name,
                    default_workspace=target_default_ws,
                    role_profile=target_role_profile
                )

                # Update DB with operational metadata
                doc.erpnext_owner_email = current_user_email
                doc.erpnext_user = current_user_email
                if temp_password:
                    doc.erpnext_password = Utility.encrypt_message(temp_password)
                doc.erpnext_site = doc.site_name
                doc.erpnext_company = doc.company_name
                doc.erpnext_roles = roles
                doc.save()

                self.update_onboarding_status(CRMOnboardingStatus.USER_CREATED)
                doc = CRMClientDetails.objects(bot=self.bot, company_name=self.company_name).first()
        except Exception as e:
            logger.error(f"[{self.provisioning_id}] User creation/assignment failed: {str(e)}")
            self.update_onboarding_status(CRMOnboardingStatus.FAILED_USER, str(e))
            return ProvisioningResult(status=CRMOnboardingStatus.FAILED_USER.value, error=str(e))

        # 6. Verification
        try:
            if doc.onboarding_status in (CRMOnboardingStatus.USER_CREATED.value, CRMOnboardingStatus.FAILED_VERIFICATION.value):
                logger.info(f"[{self.provisioning_id}] Verifying provisioning state...")

                # If smtp is disabled, we pass temp_password to test auth
                if not smtp_enabled and not temp_password:
                    temp_password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
                    logger.info(f"[{self.provisioning_id}] Rotating user password for login verification...")
                    client.login(admin_password)
                    url = f"{client.base_url}/api/resource/User/{current_user_email}"
                    client.session.put(url, json={"new_password": temp_password}, timeout=15)

                if not verifier.verify_provisioning_state(
                    admin_password=admin_password,
                    company=doc.company_name,
                    email=current_user_email,
                    required_roles=["System Manager"],
                    temp_password=temp_password
                ):
                    raise AppException("Verification failed.")

                self.update_onboarding_status(CRMOnboardingStatus.COMPLETED)
        except Exception as e:
            logger.error(f"[{self.provisioning_id}] Final verification failed: {str(e)}")
            self.update_onboarding_status(CRMOnboardingStatus.FAILED_VERIFICATION, str(e))
            return ProvisioningResult(status=CRMOnboardingStatus.FAILED_VERIFICATION.value, error=str(e))

        return ProvisioningResult(
            status=CRMOnboardingStatus.COMPLETED.value,
            site_name=doc.site_name,
            site_url=f"http://{doc.site_name}",
            company=doc.company_name,
            erpnext_user=current_user_email,
            authentication_method=auth_method,
            temporary_password=temp_password
        )
