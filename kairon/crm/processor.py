import hmac
import hashlib
import base64
import datetime
import json
import secrets
import time
import uuid
from urllib.parse import urlencode
from datetime import datetime as dt
from mongoengine.queryset.visitor import Q

from loguru import logger
from fastapi import HTTPException

from kairon.exceptions import AppException
from kairon.shared.data.constant import RE_ALPHA_NUM
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility
from kairon.crm.lead_dispatch import get_lead_webhook_secret
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus, CRMInvitation, CRMInvitationStatus
from kairon.crm.schemas import validate_email_address, normalize_email
from kairon.crm.services.admin_invitation import CRMAdminInvitationService
from kairon.crm.services.bench_executor import BenchExecutor
from kairon.crm.metering_sync import (
    CRMMeteringSync, CRM_TENANT_PROVISIONED, CRM_TENANT_PROVISION_FAILED,
)
from kairon.crm.services.erpnext_client import ERPNextClient
from kairon.crm.services.provisioning import ProvisioningService
from kairon.shared.models import User


class CRMProcessor:

    @staticmethod
    def is_crm_enabled(bot: str) -> bool:
        return MongoProcessor.is_crm_enabled(bot)

    @staticmethod
    def set_crm_enabled(bot: str, user: str, enabled: bool) -> dict:
        """The enable_crm toggle through the one authoritative path (slot provisioning and the Metering notification)."""
        from kairon.shared.data.data_objects import BotSettings
        settings = BotSettings.objects(bot=bot, status=True).first()
        if not settings:
            raise AppException("Bot Settings for the bot not found")
        analytics = settings.analytics.to_mongo().to_dict() if settings.analytics else {}
        MongoProcessor.edit_bot_settings({"enable_crm": bool(enabled), "analytics": analytics}, bot, user)
        return {"enabled": bool(enabled)}

    @staticmethod
    def save_crm_details(
        company_name: str,
        abbr: str,
        default_currency: str,
        country: str,
        bot: str,
        user: str,
        selected_modules: list = None,
        crm_admin_email: str = None,
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
                crm_admin_email=crm_admin_email,
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

    # Fields the Admin-facing API may return. This is an allowlist on purpose: the stored record also
    # holds the decrypted Administrator password, DB credentials, Frappe API key/secret, webhook
    # secrets, DB host/user, lock state and raw provisioning errors (bench tracebacks), and a new
    # model field must not become public by default.
    PUBLIC_DETAIL_FIELDS = (
        "_id",
        "company_name",
        "abbr",
        "default_currency",
        "country",
        "bot",
        "user",
        "onboarding_status",
        "site_name",
        "tier",
        "installed_apps",
        "selected_modules",
        "erpnext_company",
        "timestamp",
        "workflow_started_at",
        "workflow_completed_at",
        "attempt_number",
        "crm_admin_email",
        "invitation_status",
        "invitation_attempts",
        "invitation_sent_at",
        "invitation_next_attempt_at",
        "invitation_last_error",
    )

    # Public provisioning vocabulary over the stored state machine. No data migration: the stored statuses stay the
    # source of truth and are only grouped for display.
    PUBLIC_STATUS = {
        CRMOnboardingStatus.PENDING.value: "Pending",
        CRMOnboardingStatus.PROJECT_CREATED.value: "Provisioning",
        CRMOnboardingStatus.BENCH_RUNNING.value: "Provisioning",
        CRMOnboardingStatus.SITE_CREATED.value: "Provisioning",
        CRMOnboardingStatus.SITE_HEALTHY.value: "Configuring",
        CRMOnboardingStatus.COMPANY_CREATED.value: "Configuring",
        CRMOnboardingStatus.USER_CREATED.value: "Verifying",
        CRMOnboardingStatus.COMPLETED.value: "Ready",
        CRMOnboardingStatus.UPGRADING_TO_TIER_2.value: "Configuring",
    }

    @staticmethod
    def public_provisioning_status(onboarding_status: str) -> str:
        if not onboarding_status:
            return "Pending"
        if onboarding_status.startswith("FAILED"):
            return "Failed"
        return CRMProcessor.PUBLIC_STATUS.get(onboarding_status, "Provisioning")

    @staticmethod
    def get_provisioning_status(bot: str) -> dict:
        """Accurate, secret-free status for the Admin UI. `ready` is true only for a verified COMPLETED tenant."""
        record = CRMClientDetails.objects(bot=bot).first()
        if not record:
            raise AppException("No CRM configuration found for this bot.")
        failed = (record.onboarding_status or "").startswith("FAILED")
        return {
            "onboarding_status": record.onboarding_status,
            "status": CRMProcessor.public_provisioning_status(record.onboarding_status),
            "ready": record.onboarding_status == CRMOnboardingStatus.COMPLETED.value,
            "failed": failed,
            "company_name": record.company_name,
            "crm_admin_email": record.crm_admin_email,
            "tenant_url": CRMProcessor.get_tenant_url(record.site_name) if record.site_name else None,
            "attempt_number": record.attempt_number,
            "invitation": {
                "status": record.invitation_status or "NOT_SENT",
                "attempts": record.invitation_attempts or 0,
                "sent_at": record.invitation_sent_at.isoformat() if record.invitation_sent_at else None,
                "next_attempt_at": record.invitation_next_attempt_at.isoformat() if record.invitation_next_attempt_at else None,
                "last_error": record.invitation_last_error,
            },
        }

    @staticmethod
    def assert_staff_allowed(user_email: str):
        """
        Optional fail-closed gate for provisioning/user-management by Kairon staff. When `crm.staff_allowlist`
        (env CRM_STAFF_ALLOWLIST, comma separated emails or `@domain` suffixes) is set, only matching callers pass;
        when unset, the existing per-bot ADMIN_ACCESS rule applies unchanged.
        """
        raw = (Utility.environment.get("crm") or {}).get("staff_allowlist")
        entries = [e.strip().lower() for e in str(raw or "").split(",") if e.strip()]
        if not entries:
            return
        email = normalize_email(user_email)
        for entry in entries:
            if (entry.startswith("@") and email.endswith(entry)) or email == entry:
                return
        raise AppException("You are not authorised to manage CRM tenants.")

    @staticmethod
    def _bench_config() -> dict:
        return (Utility.environment.get("crm") or {}).get("bench") or {}

    @staticmethod
    def returns_temporary_password() -> bool:
        # Default OFF: the one-time ERPNext password is not sent to clients unless a deployment opts in
        # (BENCH_ONBOARD_RETURN_TEMP_PASSWORD=true). Creators sign in with the one-click login link instead.
        value = CRMProcessor._bench_config().get("onboard_return_temporary_password")
        return str(value or "").lower() in ("1", "true", "yes")

    @staticmethod
    def get_tenant_url(site_name: str) -> str:
        """
        Public URL of a provisioned tenant site (same form as ProvisioningResult.site_url).
        Default is `http://<site>`. Deployments set `crm.bench.tenant_url_scheme` (env BENCH_TENANT_URL_SCHEME,
        `https` in production) and, when the bench frontend is not on the default port (e.g. a local stack on
        :8080), `crm.bench.tenant_url_port` (env BENCH_TENANT_URL_PORT) so the link actually opens.
        """
        if not site_name:
            return None
        bench = CRMProcessor._bench_config()
        scheme = str(bench.get("tenant_url_scheme") or "http").lower()
        if scheme not in ("http", "https"):
            raise AppException("crm.bench.tenant_url_scheme must be 'http' or 'https'.")
        port = bench.get("tenant_url_port")
        return f"{scheme}://{site_name}:{int(port)}" if port else f"{scheme}://{site_name}"

    @staticmethod
    def get_crm_public_details(bot: str) -> dict:
        """
        Tenant configuration + provisioning state for API consumers (Kairon Admin): only the
        PUBLIC_DETAIL_FIELDS of the stored record, plus the derived tenant `site_url`.
        """
        data = {
            k: v
            for k, v in CRMProcessor.get_crm_details(bot).items()
            if k in CRMProcessor.PUBLIC_DETAIL_FIELDS
        }
        data["site_url"] = CRMProcessor.get_tenant_url(data.get("site_name"))
        return data

    @staticmethod
    def sync_metering_metadata(bot: str, company_name: str = None) -> dict:
        """
        Sends the tenant's final state (COMPLETED or FAILED_*) to Metering and records the outcome on
        the CRMClientDetails record. Built from the authoritative Kairon record each time, so it is
        safe to call again after a failed delivery (the event id is derived from the provisioning run,
        and Metering ignores duplicates). Never sends credentials or raw error text.
        """
        query = {"bot": bot}
        if company_name:
            query["company_name__iexact"] = company_name.strip()
        record = CRMClientDetails.objects(**query).first()
        if not record:
            raise AppException("No CRM configuration found for this bot.")
        status = record.onboarding_status
        if status == CRMOnboardingStatus.COMPLETED.value:
            event_type = CRM_TENANT_PROVISIONED
        elif status and status.startswith("FAILED"):
            event_type = CRM_TENANT_PROVISION_FAILED
        else:
            raise AppException("Provisioning has not finished; there is nothing to send to Metering yet.")

        payload = {
            "bot": record.bot,
            "user": record.user,
            "company_name": record.company_name,
            "company_abbr": record.abbr,
            "country": record.country,
            "currency": record.default_currency,
            "provisioning_status": status,
        }
        if event_type == CRM_TENANT_PROVISIONED:
            payload.update(
                tenant_name=record.site_name,
                tenant_url=CRMProcessor.get_tenant_url(record.site_name),
                tier=record.tier,
            )
        run_id = record.provisioning_id or "no_run"
        event_id = f"evt_{run_id}_{event_type}"
        if record.metering_synced:
            # Already delivered once. An explicit re-sync gets an id that also covers the payload: identical
            # content -> identical id (Metering ignores it), changed content (e.g. a corrected tenant URL)
            # -> a new id, so Metering applies the update instead of treating it as a duplicate.
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:10]
            event_id = f"{event_id}_{digest}"
        result = CRMMeteringSync.publish(event_type, payload, event_id=event_id, correlation_id=run_id)
        if result["sent"]:
            record.update(
                set__metering_synced=True,
                set__metering_synced_at=datetime.datetime.utcnow(),
                set__metering_event_id=result["event_id"],
            )
        elif result["reason"] != "not_configured":
            record.update(set__metering_synced=False)
        return {"synced": result["sent"], "event_id": result["event_id"], "reason": result["reason"]}

    @staticmethod
    def _notify_metering(bot: str, company_name: str):
        """Best-effort handoff after an onboarding run; must never affect the onboarding result."""
        try:
            CRMProcessor.sync_metering_metadata(bot, company_name)
        except Exception as e:
            logger.warning(f"[CRMProcessor] Metering handoff skipped for bot {bot}: {e}")

    @staticmethod
    def onboarding_outcome(result: dict) -> dict:
        """
        Makes the real provisioning outcome explicit without removing any existing field (the Streamlit app, the
        E2E suite and Admin read `status`). `accepted` only says the request was valid and a run was attempted;
        `provisioned` is True only for a COMPLETED tenant; `failed` is True for any FAILED_* terminal state.
        """
        result = dict(result or {})
        status = result.get("status")
        result["accepted"] = True
        result["provisioned"] = status == CRMOnboardingStatus.COMPLETED.value
        result["failed"] = isinstance(status, str) and status.startswith("FAILED")
        return result

    LOGIN_LINK_TTL_SECONDS = 60

    @staticmethod
    def build_login_link(bot: str, requester_email: str) -> dict:
        """
        One-time login link for the user who created the tenant ("Open ERPNext"). Signed with the tenant webhook
        secret Kairon already holds, using the same HMAC scheme as its events; kairon_connector verifies it, enforces
        the 60 second window and single use, and logs that one user in. Only the creator may request it, only for a
        COMPLETED tenant, and the secret itself never leaves Kairon.
        """
        record = CRMClientDetails.objects(bot=bot).first()
        if not record or record.onboarding_status != CRMOnboardingStatus.COMPLETED.value:
            raise AppException("The CRM tenant is not ready yet.")
        owner = (record.erpnext_user or "").strip().lower()
        if not owner or (requester_email or "").strip().lower() != owner:
            raise AppException("Only the user who created this CRM tenant can open it with one-click login.")

        tenant_url = CRMProcessor.get_tenant_url(record.site_name)
        allow_http = str(CRMProcessor._bench_config().get("sso_allow_insecure_http") or "").lower() in ("1", "true", "yes")
        if not tenant_url.startswith("https://") and not allow_http:
            # The link is a short-lived credential; never send it over plain HTTP unless a developer opted in.
            raise AppException(
                "One-click login is disabled because the tenant URL is not HTTPS. Set BENCH_TENANT_URL_SCHEME=https "
                "(production) or BENCH_SSO_ALLOW_INSECURE_HTTP=true (local development only)."
            )
        secret = CRMProcessor.get_lead_webhook_secret(bot)
        nonce = secrets.token_urlsafe(18)
        ts = str(int(time.time()))  # epoch seconds; utcnow().timestamp() would be skewed by the local UTC offset
        payload = f"sso.v1|{record.site_name}|{record.erpnext_user}|{nonce}".encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + payload, hashlib.sha256).hexdigest()
        query = urlencode({"user": record.erpnext_user, "ts": ts, "nonce": nonce, "sig": "sha256=" + sig})
        url = f"{tenant_url}/api/method/kairon_connector.api.v1.sso.login?{query}"
        return {"login_url": url, "expires_in": CRMProcessor.LOGIN_LINK_TTL_SECONDS}

    @staticmethod
    def validate_tenant_config(
        bot: str, company_name: str, abbr: str, default_currency: str, country: str
    ) -> dict:
        """
        Side-effect free pre-check for an onboarding request: CRM must be enabled for the bot
        and the company name must be valid and not already registered for it.
        """
        if not MongoProcessor.is_crm_enabled(bot):
            raise AppException("CRM integration is not enabled")
        for label, value in (
            ("Company Name", company_name), ("Abbr", abbr),
            ("Default Currency", default_currency), ("Country", country),
        ):
            if Utility.check_empty_string(value):
                raise AppException(f"{label} cannot be empty.")
        if not Utility.special_match(company_name, search=RE_ALPHA_NUM):
            raise AppException(
                "Company name can only contain letters, numbers, spaces and underscores."
            )
        existing = CRMClientDetails.objects(
            bot=bot, company_name__iexact=company_name.strip()
        ).first()
        return {
            "valid": True,
            "company_exists": existing is not None,
            "onboarding_status": existing.onboarding_status if existing else None,
        }

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
        # COMPLETED gates lead creation, invitations and the public "Ready" status, so adding a user to a tenant that
        # is already provisioned must not push it back into the provisioning state machine.
        if record and record.onboarding_status != CRMOnboardingStatus.COMPLETED.value:
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
        crm_admin_email: str = None,
    ):
        if not MongoProcessor.is_crm_enabled(bot):
            raise AppException("CRM integration is not enabled")
        CRMProcessor.assert_staff_allowed(current_user.email)
        try:
            crm_admin_email = validate_email_address(crm_admin_email, "CRM administrator email")
        except ValueError as e:
            raise AppException(str(e))

        # 1. Save or get the initial CRMClientDetails document
        existing = CRMClientDetails.objects(bot=bot, company_name__iexact=company_name.strip()).first()
        if existing and existing.crm_admin_email != crm_admin_email:
            # Once the administrator account exists it is managed through user management, not re-onboarding.
            if existing.onboarding_status == CRMOnboardingStatus.COMPLETED.value or (
                existing.crm_admin_email and existing.onboarding_status in (
                    CRMOnboardingStatus.USER_CREATED.value, CRMOnboardingStatus.FAILED_VERIFICATION.value)
            ):
                raise AppException(
                    "This tenant already has a CRM administrator. Use user management to change administrators."
                )
            existing.crm_admin_email = crm_admin_email
            existing.save()
        if not existing:
            CRMProcessor.save_crm_details(
                company_name=company_name,
                abbr=abbr,
                default_currency=default_currency,
                country=country,
                bot=bot,
                user=current_user.get_user(),
                selected_modules=selected_modules,
                crm_admin_email=crm_admin_email,
            )
        elif selected_modules is not None:
            existing.selected_modules = selected_modules
            existing.save()

        # 2. Acquire Atomic Provisioning Lock
        # We allow acquisition if lock=False or if the lock is older than 2 hours (stale lock recovery)
        stale_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=2)

        query = (Q(bot=bot) & Q(company_name__iexact=company_name.strip()))
        lock_condition = Q(lock=False) | Q(lock_timestamp__lt=stale_threshold)

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
            local_part = crm_admin_email.split("@", 1)[0]
            result = service.execute_onboarding_workflow(
                current_user_email=crm_admin_email,
                first_name=(local_part.replace(".", " ").replace("_", " ").title() or "CRM")[:60],
                last_name="Administrator"
            )

            # The lock is released inside execute_onboarding_workflow (via update_onboarding_status)
            CRMProcessor._notify_metering(bot, company_name)
            if result.status == CRMOnboardingStatus.COMPLETED.value and not service.admin_already_active:
                # Readiness is verified at this point; delivery is attempted off the request path and retried by the
                # scheduled job, and its outcome never changes the provisioning status. An administrator who has
                # already signed in (nothing to set up) is not sent a setup link.
                if CRMAdminInvitationService.mark_pending(bot, company_name, provisioning_id):
                    CRMAdminInvitationService.send_in_background(bot)
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
            CRMProcessor._notify_metering(bot, company_name)
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
        return get_lead_webhook_secret(bot)

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
        bot: str = None,
    ) -> dict:
        """
        Processes an incoming ERPNext webhook for a UserInvitation acceptance.
        Called by the public webhook receiver endpoint.

        Security: Verifies the HMAC-SHA256 signature using the per-site webhook_secret
        stored in CRMClientDetails. Rejects requests that fail verification.

        Returns a summary dict of actions taken.
        """
        # An unknown site, a site that belongs to another bot and a bad signature all answer the same way, so the
        # public endpoint cannot be used to discover which tenant sites exist. The reason is logged, not returned.
        doc = CRMClientDetails.objects(site_name=site_name).first()
        if not doc or (bot is not None and doc.bot != bot):
            logger.warning(f"[CRMProcessor] Webhook rejected: site '{site_name}' is unknown or not owned by the requested bot")
            raise AppException("Invalid webhook signature.")

        # Verify HMAC-SHA256 signature
        if not doc.webhook_secret:
            logger.warning(f"[CRMProcessor] Webhook rejected: no webhook secret configured for site '{site_name}'")
            raise AppException("Invalid webhook signature.")

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
    def _reconcile_invitation(client, site_doc, company: str, inv, app_name: str, summary: dict) -> None:
        """Brings one PENDING invitation in line with its ERPNext state, updating `summary`. Raises on any failure."""
        erpnext_inv = client.get_invitation_status(inv.email, app_name)
        if not erpnext_inv:
            return
        erpnext_status = erpnext_inv.get("status")
        if erpnext_status == "Accepted":
            if not client.check_user_exists(inv.email):
                return
            if site_doc.tier == 2:  # Tier 1 sites have no Company doctype
                client.assign_company_permission(inv.email, company)
            now = dt.utcnow()
            inv.update(
                set__invitation_status=CRMInvitationStatus.COMPANY_ASSIGNED.value,
                set__accepted_at=now,
                set__company_assigned_at=now,
            )
            summary["assigned"] += 1
            logger.info(f"[reconcile] Assigned company permission: email={inv.email}, site={site_doc.site_name}")
        elif erpnext_status == "Expired":
            inv.update(set__invitation_status=CRMInvitationStatus.EXPIRED.value)
            summary["expired"] += 1
        elif erpnext_status == "Cancelled":
            inv.update(set__invitation_status=CRMInvitationStatus.CANCELLED.value)
            summary["cancelled"] += 1

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
                    CRMProcessor._reconcile_invitation(client, site_doc, company, inv, app_name, summary)
                except Exception as e:
                    logger.error(f"[reconcile] Error processing invitation for '{inv.email}' on '{site_name}': {e}")
                    summary["errors"] += 1

        logger.info(f"[reconcile] Reconciliation complete: {summary}")
        return summary

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
