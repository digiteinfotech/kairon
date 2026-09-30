import hmac
import hashlib
import base64
import datetime
import uuid
from datetime import datetime as dt
from mongoengine.queryset.visitor import Q

from loguru import logger
from fastapi import HTTPException

from kairon.exceptions import AppException
from kairon.shared.data.constant import RE_ALPHA_NUM
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus, CRMInvitation, CRMInvitationStatus
from kairon.crm.services.bench_executor import BenchExecutor
from kairon.crm.services.erpnext_client import ERPNextClient
from kairon.crm.services.provisioning import ProvisioningService
from kairon.shared.models import User


class CRMProcessor:

    @staticmethod
    def is_crm_enabled(bot: str) -> bool:
        return MongoProcessor.is_crm_enabled(bot)

    @staticmethod
    def save_crm_details(
        company_name: str,
        abbr: str,
        default_currency: str,
        country: str,
        bot: str,
        user: str,
        selected_modules: list = None,
    ):
        if Utility.check_empty_string(company_name):
            raise AppException("Company Name cannot be empty.")

        if not Utility.special_match(company_name, search=RE_ALPHA_NUM):
            raise AppException(
                "Company name can only contain letters, numbers, spaces and underscores."
            )

        if Utility.check_empty_string(abbr):
            raise AppException("Abbr cannot be empty.")

        if Utility.check_empty_string(default_currency):
            raise AppException("Default Currency cannot be empty.")

        if Utility.check_empty_string(country):
            raise AppException("Country cannot be empty.")

        Utility.is_exist(
            CRMClientDetails,
            exp_message="Company already exists for this bot.",
            bot=bot,
            company_name__iexact=company_name.strip(),
            check_base_fields=False,
        )

        record = (
            CRMClientDetails(
                company_name=company_name.strip(),
                abbr=abbr.strip(),
                default_currency=default_currency.strip(),
                country=country.strip(),
                bot=bot.strip(),
                user=user.strip(),
                onboarding_status=CRMOnboardingStatus.PENDING.value,
                selected_modules=selected_modules or [],
            )
            .save()
            .to_mongo()
            .to_dict()
        )
        if "_id" in record:
            record["_id"] = str(record["_id"])
        return record

    @staticmethod
    def get_crm_details(bot: str):
        record = CRMClientDetails.objects(bot=bot).first()
        if not record:
            raise AppException("No CRM configuration found for this bot.")

        data = record.to_mongo().to_dict()
        if "_id" in data:
            data["_id"] = str(data["_id"])
        if "selected_modules" in data and data["selected_modules"] is not None:
            data["selected_modules"] = list(data["selected_modules"])

        if data.get("erpnext_password"):
            try:
                data["erpnext_password"] = Utility.decrypt_message(data["erpnext_password"])
            except Exception as e:
                logger.debug(f"[CRMProcessor] Failed to decrypt stored erpnext_password: {e}")

        return data

    @staticmethod
    def update_onboarding_status(
        bot: str, company_name: str, status: CRMOnboardingStatus
    ):
        record = CRMClientDetails.objects(
            bot=bot, company_name__iexact=company_name.strip()
        ).first()
        if not record:
            raise AppException("CRM configuration not found.")

        record.onboarding_status = status.value
        record.save()

    @staticmethod
    def delete_crm_details(bot: str, company_name: str):
        if Utility.check_empty_string(company_name):
            raise AppException("Company name cannot be empty.")

        record = CRMClientDetails.objects(
            bot=bot, company_name__iexact=company_name.strip()
        ).first()
        if not record:
            raise HTTPException(
                400, detail=f"Company '{company_name}' not found."
            )

        record.delete()
        return {
            "success": True,
            "message": f"Company '{company_name}' details removed successfully.",
        }

    @staticmethod
    def create_crm_user(bot: str, user: str, email: str, role: str):
        logger.info(
            f"Creating CRM user: bot={bot}, user={user}, email={email}, role={role}"
        )
        result = BenchExecutor().create_crm_user(bot, email, role)
        record = CRMClientDetails.objects(bot=bot).first()
        if record:
            CRMProcessor.update_onboarding_status(
                bot, record.company_name, CRMOnboardingStatus.USER_CREATED
            )
        return result

    def onboard_company(
        self,
        company_name: str,
        abbr: str,
        default_currency: str,
        country: str,
        bot: str,
        current_user: User,
        selected_modules: list = None,
    ):
        if not MongoProcessor.is_crm_enabled(bot):
            raise AppException("CRM integration is not enabled")

        # 1. Save or get the initial CRMClientDetails document
        existing = CRMClientDetails.objects(bot=bot, company_name__iexact=company_name.strip()).first()
        if not existing:
            CRMProcessor.save_crm_details(
                company_name=company_name,
                abbr=abbr,
                default_currency=default_currency,
                country=country,
                bot=bot,
                user=current_user.get_user(),
                selected_modules=selected_modules,
            )
        elif selected_modules is not None:
            existing.selected_modules = selected_modules
            existing.save()

        # 2. Acquire Atomic Provisioning Lock
        # We allow acquisition if lock=False or if the lock is older than 2 hours (stale lock recovery)
        stale_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        
        # Terminal states where we can definitely start
        terminal_states = [
            CRMOnboardingStatus.PENDING.value,
            CRMOnboardingStatus.COMPLETED.value,
            CRMOnboardingStatus.FAILED_PROJECT.value,
            CRMOnboardingStatus.FAILED_BENCH.value,
            CRMOnboardingStatus.FAILED_HEALTH.value,
            CRMOnboardingStatus.FAILED_COMPANY.value,
            CRMOnboardingStatus.FAILED_USER.value,
            CRMOnboardingStatus.FAILED_VERIFICATION.value
        ]

        query = (Q(bot=bot) & Q(company_name__iexact=company_name.strip()))
        lock_condition = Q(lock=False) | Q(lock_timestamp__lt=stale_threshold) | Q(onboarding_status__in=terminal_states)
        
        provisioning_id = str(uuid.uuid4())
        
        # Find and Update atomically
        updated_count = CRMClientDetails.objects(query & lock_condition).update_one(
            set__lock=True,
            set__lock_timestamp=datetime.datetime.utcnow(),
            set__provisioning_id=provisioning_id,
            set__workflow_started_at=datetime.datetime.utcnow(),
            inc__attempt_number=1
        )
        
        if updated_count == 0:
            raise AppException("Provisioning workflow is already in progress for this company.")

        logger.info(f"[{provisioning_id}] Atomic lock acquired for {company_name}")

        try:
            # 3. Delegate completely to ProvisioningService
            service = ProvisioningService(bot, company_name.strip(), provisioning_id)
            result = service.execute_onboarding_workflow(
                current_user_email=current_user.email,
                first_name=current_user.first_name,
                last_name=current_user.last_name
            )
            
            # The lock is released inside execute_onboarding_workflow (via update_onboarding_status)
            return result.dict()
            
        except Exception as e:
            logger.exception(f"[{provisioning_id}] Unhandled exception in ProvisioningService: {e}")
            # Ensure lock is released on catastrophic unhandled exception. Do NOT
            # force a specific onboarding_status here -- ProvisioningService already
            # records the correct stage-specific FAILED_* status for every error it
            # catches internally, and overwriting that with a fixed value breaks the
            # step guards in execute_onboarding_workflow on the next retry (each step
            # only runs when the status matches its expected prior state).
            CRMClientDetails.objects(bot=bot, company_name__iexact=company_name.strip()).update_one(
                set__lock=False,
                set__last_error=str(e)
            )
            raise e

    @staticmethod
    def _get_integration_client(doc: CRMClientDetails) -> ERPNextClient:
        """
        Builds an ERPNextClient authenticated with the dedicated kairon-crm
        integration user's token credentials. Raises AppException if credentials
        are missing (site provisioned before this feature was added).
        """
        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        base_url = bench_config.get("base_url", "http://localhost:8080")

        client = ERPNextClient(base_url, doc.site_name)
        if doc.kairon_api_key and doc.kairon_api_secret:
            api_key = Utility.decrypt_message(doc.kairon_api_key)
            api_secret = Utility.decrypt_message(doc.kairon_api_secret)
            client.authenticate_with_token(api_key, api_secret)
        else:
            if not doc.erpnext_password:
                raise AppException(
                    f"No stored credentials for tenant '{doc.site_name}' and no API key/secret on file; "
                    "cannot authenticate as the integration client."
                )
            pwd = Utility.decrypt_message(doc.erpnext_password)
            client.login(pwd)
        return client

    @staticmethod
    def get_lead_webhook_secret(bot: str) -> str:
        """
        Returns the decrypted per-tenant secret used to sign outbound Kairon events
        (lead.qualified, conversation.message.received, ...) so a KaironEventPublisher
        call can authenticate against this tenant's kairon_connector webhook gateway.
        """
        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc or not doc.lead_webhook_secret:
            raise AppException("Lead webhook secret not configured for this bot. Is provisioning COMPLETED?")
        return Utility.decrypt_message(doc.lead_webhook_secret)

    @classmethod
    def get_erpnext_users(cls, bot: str) -> list:
        """
        Fetches all users from the provisioned ERPNext site.
        """
        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc or doc.onboarding_status != CRMOnboardingStatus.COMPLETED.value:
            raise AppException("CRM provisioning is not completed for this bot.")

        client = CRMProcessor._get_integration_client(doc)
        return client.get_users()

    @staticmethod
    def invite_erpnext_user(
        bot: str,
        email: str,
        roles: list,
        company_name: str = None,
        user: str = "SYSTEM",
    ) -> dict:
        """
        Sends a native ERPNext user invitation via the UserInvitation API.
        Does NOT create users manually (no POST /api/resource/User).

        Primary flow:
          ERPNext dispatches the invitation email immediately after_insert.
          On acceptance, ERPNext fires an on_update webhook to Kairon's receiver,
          which assigns the company permission automatically (~5-10 seconds).

        Returns a dict with status: 'invited' | 'already_pending' | 'already_accepted'
        Raises AppException for error conditions (SMTP, invalid role, etc.).
        """
        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc:
            raise AppException("No CRM configuration found for this bot.")

        if doc.onboarding_status != CRMOnboardingStatus.COMPLETED.value:
            raise AppException(
                f"ERPNext site is not yet provisioned for this bot. "
                f"Current status: {doc.onboarding_status}"
            )

        company = company_name or doc.erpnext_company or doc.company_name

        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        app_name = bench_config.get("app_name", "frappe")
        redirect_to_path = bench_config.get("invite_redirect_path", "/")

        client = CRMProcessor._get_integration_client(doc)

        # Guard: fail fast if SMTP is not configured
        if not client.check_smtp_configured():
            raise AppException(
                "ERPNext SMTP not configured. Configure an outgoing Email Account "
                "in ERPNext before inviting users."
            )

        result = client.invite_user(email, roles, redirect_to_path, app_name)

        # Parse ERPNext's categorised response
        if email in (result.get("disabled_user_emails") or []):
            raise AppException(f"User '{email}' is disabled in ERPNext.")

        if email in (result.get("accepted_invite_emails") or []):
            logger.info(f"[CRMProcessor] Invitation already accepted for '{email}'.")
            return {"status": "already_accepted", "email": email, "company": company}

        if email in (result.get("pending_invite_emails") or []):
            logger.info(f"[CRMProcessor] Invitation already pending for '{email}'.")
            return {"status": "already_pending", "email": email, "company": company}

        # Success: new invitation dispatched
        inv_record = client.get_invitation_status(email, app_name)
        erpnext_invitation_id = inv_record.get("name") if inv_record else None

        CRMInvitation(
            bot=bot,
            user=user,
            site_name=doc.site_name,
            company=company,
            email=email,
            roles=roles,
            invitation_status=CRMInvitationStatus.PENDING.value,
            erpnext_invitation_id=erpnext_invitation_id,
            invited_at=dt.utcnow(),
        ).save()

        logger.info(
            f"[CRMProcessor] Invitation sent: site={doc.site_name}, company={company}, "
            f"email={email}, roles={roles}, erpnext_id={erpnext_invitation_id}"
        )
        return {
            "status": "invited",
            "email": email,
            "roles": roles,
            "company": company,
            "site": doc.site_name,
        }

    @staticmethod
    def handle_invitation_webhook(
        site_name: str,
        raw_body: bytes,
        signature_header: str,
        payload: dict,
    ) -> dict:
        """
        Processes an incoming ERPNext webhook for a UserInvitation acceptance.
        Called by the public webhook receiver endpoint.

        Security: Verifies the HMAC-SHA256 signature using the per-site webhook_secret
        stored in CRMClientDetails. Rejects requests that fail verification.

        Returns a summary dict of actions taken.
        """
        doc = CRMClientDetails.objects(site_name=site_name).first()
        if not doc:
            logger.warning(f"[CRMProcessor] Webhook received for unknown site: '{site_name}'")
            raise AppException(f"Unknown site: {site_name}")

        # Verify HMAC-SHA256 signature
        if not doc.webhook_secret:
            raise AppException("Webhook secret not configured for this site.")

        secret = Utility.decrypt_message(doc.webhook_secret)
        expected_sig = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")

        if not hmac.compare_digest(expected_sig, signature_header or ""):
            logger.error(f"[CRMProcessor] Webhook signature mismatch for site '{site_name}'")
            raise AppException("Invalid webhook signature.")

        # Extract invitation data
        status = payload.get("status")
        email = payload.get("email")

        if status != "Accepted" or not email:
            logger.info(f"[CRMProcessor] Webhook ignored: status={status}, email={email}")
            return {"action": "ignored", "reason": f"status={status}"}

        logger.info(f"[CRMProcessor] Processing acceptance webhook: site={site_name}, email={email}")

        client = CRMProcessor._get_integration_client(doc)
        company = doc.erpnext_company or doc.company_name

        # Defensive check: user must exist before we assign permissions
        if not client.check_user_exists(email):
            logger.warning(f"[CRMProcessor] Webhook accepted but user '{email}' not yet visible. Deferring to reconciler.")
            return {"action": "deferred", "reason": "user_not_found"}

        try:
            # Tier 1 (standalone CRM) sites have no ERPNext Company doctype, so there is no company
            # to scope the user to (provisioning likewise skips company assignment for Tier 1).
            if doc.tier == 2:
                client.assign_company_permission(email, company)
        except AppException as e:
            # Log and record the error; the reconciler will retry
            inv = CRMInvitation.objects(site_name=site_name, email=email, invitation_status=CRMInvitationStatus.PENDING.value).first()
            if inv:
                inv.last_error = str(e)
                inv.save()
            logger.error(f"[CRMProcessor] Company permission assignment failed for '{email}': {e}")
            raise

        # Update CRMInvitation audit record
        now = dt.utcnow()
        updated = CRMInvitation.objects(
            site_name=site_name,
            email=email,
            invitation_status=CRMInvitationStatus.PENDING.value,
        ).update_one(
            set__invitation_status=CRMInvitationStatus.COMPANY_ASSIGNED.value,
            set__accepted_at=now,
            set__company_assigned_at=now,
        )

        logger.info(f"[CRMProcessor] Webhook processed: company permission assigned for '{email}' on '{site_name}'. Records updated: {updated}")
        return {"action": "company_permission_assigned", "email": email, "site": site_name}

    @staticmethod
    def reconcile_invitations(bot: str = None) -> dict:
        """
        Fallback safety-net for missed webhooks.
        Runs every 30 minutes via the Kairon scheduler.
        Checks all Pending CRMInvitation records against ERPNext and assigns
        company permissions for any that have been accepted but whose webhook was missed.
        """
        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        app_name = bench_config.get("app_name", "frappe")

        query = CRMInvitation.objects(invitation_status=CRMInvitationStatus.PENDING.value)
        if bot:
            query = query.filter(bot=bot)

        pending = list(query)
        summary = {"checked": len(pending), "assigned": 0, "expired": 0, "cancelled": 0, "errors": 0}

        # Group by site to minimise client instantiation
        sites: dict = {}
        for inv in pending:
            sites.setdefault(inv.site_name, []).append(inv)

        for site_name, invitations in sites.items():
            site_doc = CRMClientDetails.objects(site_name=site_name).first()
            if not site_doc:
                logger.warning(f"[reconcile] No CRMClientDetails for site '{site_name}'. Skipping.")
                continue
            try:
                client = CRMProcessor._get_integration_client(site_doc)
                company = site_doc.erpnext_company or site_doc.company_name
            except AppException as e:
                logger.error(f"[reconcile] Cannot build client for site '{site_name}': {e}")
                summary["errors"] += len(invitations)
                continue

            for inv in invitations:
                try:
                    erpnext_inv = client.get_invitation_status(inv.email, app_name)
                    if not erpnext_inv:
                        continue

                    erpnext_status = erpnext_inv.get("status")
                    now = dt.utcnow()

                    if erpnext_status == "Accepted":
                        if client.check_user_exists(inv.email):
                            if site_doc.tier == 2:  # Tier 1 sites have no Company doctype
                                client.assign_company_permission(inv.email, company)
                            inv.update(
                                set__invitation_status=CRMInvitationStatus.COMPANY_ASSIGNED.value,
                                set__accepted_at=now,
                                set__company_assigned_at=now,
                            )
                            summary["assigned"] += 1
                            logger.info(f"[reconcile] Assigned company permission: email={inv.email}, site={site_name}")
                    elif erpnext_status == "Expired":
                        inv.update(set__invitation_status=CRMInvitationStatus.EXPIRED.value)
                        summary["expired"] += 1
                    elif erpnext_status == "Cancelled":
                        inv.update(set__invitation_status=CRMInvitationStatus.CANCELLED.value)
                        summary["cancelled"] += 1

                except Exception as e:
                    logger.error(f"[reconcile] Error processing invitation for '{inv.email}' on '{site_name}': {e}")
                    summary["errors"] += 1

        logger.info(f"[reconcile] Reconciliation complete: {summary}")
        return summary

    @staticmethod
    def get_db_tables(bot: str) -> list:
        record = CRMClientDetails.objects(bot=bot).first()
        if not record or not record.site_name:
            raise AppException("No site found for this bot to fetch database tables.")
        return BenchExecutor().get_db_tables(record.site_name)

    @staticmethod
    def get_table_content(bot: str, table_name: str, limit: int = 50) -> list:
        record = CRMClientDetails.objects(bot=bot).first()
        if not record or not record.site_name:
            raise AppException("No site found for this bot to fetch table content.")
        return BenchExecutor().get_table_content(record.site_name, table_name, limit)

    @staticmethod
    def get_available_modules(bot: str = None) -> dict:
        if bot:
            doc = CRMClientDetails.objects(bot=bot).first()
            if doc and doc.site_name and doc.onboarding_status == CRMOnboardingStatus.COMPLETED.value:
                try:
                    client = CRMProcessor._get_integration_client(doc)
                    return client.discover_business_modules()
                except Exception as e:
                    logger.warning(f"[CRMProcessor] Live module discovery failed for bot '{bot}': {e}. Using static catalog.")

        from kairon.crm.constants import BUSINESS_MODULE_CATALOG
        modules = [
            {
                "key": key,
                "workspace": cat["workspace"],
                "frappe_module": cat["frappe_module"],
                "description": cat["description"]
            }
            for key, cat in BUSINESS_MODULE_CATALOG.items()
        ]
        return {"source": "static_fallback", "modules": modules}

    @staticmethod
    def get_selected_modules(bot: str) -> dict:
        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc:
            raise AppException("No CRM configuration found for this bot.")

        from kairon.crm.constants import DEFAULT_MODULE_SELECTION
        selected = list(doc.selected_modules) if doc.selected_modules else list(DEFAULT_MODULE_SELECTION)
        return {
            "bot": bot,
            "company_name": doc.company_name,
            "selected_modules": selected,
            "module_profile_name": doc.module_profile_name
        }

    @staticmethod
    def configure_modules(bot: str, user: str, selected_modules: list) -> dict:
        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc:
            raise AppException("No CRM configuration found for this bot.")

        from kairon.crm.schemas import validate_module_selection
        validated_selection = validate_module_selection(selected_modules)
        doc.selected_modules = validated_selection

        if doc.site_name and doc.onboarding_status == CRMOnboardingStatus.COMPLETED.value:
            try:
                client = CRMProcessor._get_integration_client(doc)
                disc = client.discover_business_modules()
                catalog = {m["key"]: m for m in disc["modules"]}

                # 1. Workspace hiding
                client.configure_workspace_visibility(validated_selection, catalog=catalog)

                # 2. Module Profile creation/update
                profile_name = doc.module_profile_name or f"Kairon CRM Profile ({doc.company_name})"
                blocked_modules = [m["frappe_module"] for k, m in catalog.items() if k not in validated_selection]
                client.create_or_update_module_profile(profile_name, blocked_modules)
                doc.module_profile_name = profile_name

                # 3. Assign profile to user if owner user exists
                if doc.erpnext_owner_email and client.check_user_exists(doc.erpnext_owner_email):
                    client.assign_module_profile_to_user(doc.erpnext_owner_email, profile_name)

            except Exception as e:
                logger.error(f"[CRMProcessor] Live module configuration failed for bot '{bot}': {e}")
                raise AppException(f"Failed to update module configuration in ERPNext: {str(e)}")

        doc.save()
        return {
            "success": True,
            "selected_modules": list(doc.selected_modules),
            "module_profile_name": doc.module_profile_name
        }

    @staticmethod
    def reconcile_modules(bot: str, user: str) -> dict:
        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc:
            raise AppException("No CRM configuration found for this bot.")

        if not doc.site_name or doc.onboarding_status != CRMOnboardingStatus.COMPLETED.value:
            raise AppException(f"ERPNext site is not yet provisioned for this bot. Current status: {doc.onboarding_status}")

        from kairon.crm.constants import DEFAULT_MODULE_SELECTION

        client = CRMProcessor._get_integration_client(doc)
        selected_mods = list(doc.selected_modules) if doc.selected_modules else list(DEFAULT_MODULE_SELECTION)

        # 1. Verify current configuration
        report = client.verify_module_configuration(selected_mods, profile_name=doc.module_profile_name, user_email=doc.erpnext_owner_email)

        # 2. If drift detected, repair live state
        if not report.is_fully_consistent:
            logger.info(f"[CRMProcessor] Configuration drift detected on site '{doc.site_name}'. Repairing...")
            disc = client.discover_business_modules()
            catalog = {m["key"]: m for m in disc["modules"]}

            client.configure_workspace_visibility(selected_mods, catalog=catalog)

            profile_name = doc.module_profile_name or f"Kairon CRM Profile ({doc.company_name})"
            blocked_modules = [m["frappe_module"] for k, m in catalog.items() if k not in selected_mods]
            client.create_or_update_module_profile(profile_name, blocked_modules)
            doc.module_profile_name = profile_name
            doc.save()

            if doc.erpnext_owner_email and client.check_user_exists(doc.erpnext_owner_email):
                client.assign_module_profile_to_user(doc.erpnext_owner_email, profile_name)

            # Re-verify post repair
            report = client.verify_module_configuration(selected_mods, profile_name=doc.module_profile_name, user_email=doc.erpnext_owner_email)

        return report.dict()


