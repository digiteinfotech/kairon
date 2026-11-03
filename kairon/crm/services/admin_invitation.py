"""
CRM administrator invitation: emails the configured administrator the tenant URL and a single-use password-setup link
once, and only once, the tenant is verified ready.

Guarantees
- Only for `COMPLETED` tenants. Provisioning state is never changed by delivery success or failure.
- At most one worker sends per attempt: an atomic Mongo claim (`PENDING|FAILED -> SENDING`).
- The setup link is requested from the tenant's connector at send time, held in memory for the one email, and never
  stored or logged. It is Frappe's own reset-password key (single use, expires per the tenant's System Settings).
- Failures are recorded (attempts, next attempt, short error class) and retried with exponential backoff by the
  scheduled job, or on demand through the resend endpoint.
"""
import asyncio
import html
import re
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Text

from loguru import logger

from kairon.crm.models import CRMClientDetails, CRMAdminInvitationStatus, CRMOnboardingStatus
from kairon.crm.services.connector_client import ConnectorUserClient
from kairon.exceptions import AppException
from kairon.shared.utils import Utility, MailUtility

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 3600
CLAIM_STALE_SECONDS = 600
RESEND_COOLDOWN_SECONDS = 60
_SECRET_LIKE = re.compile(r"(key|token|sig|password|secret)=[^\s&\"']+", re.IGNORECASE)


def _safe_error(error: Exception) -> Text:
    return _SECRET_LIKE.sub(r"\1=***", f"{type(error).__name__}: {error}")[:300]


class CRMAdminInvitationService:

    @staticmethod
    def mark_pending(bot: Text, company_name: Text, provisioning_id: Optional[Text]) -> bool:
        """
        Called when a run reaches COMPLETED. Arms the invitation exactly once per provisioning run, so repeated
        onboard calls on a finished tenant do not queue another email.
        """
        updated = CRMClientDetails.objects(
            bot=bot, company_name__iexact=company_name.strip(),
            onboarding_status=CRMOnboardingStatus.COMPLETED.value,
            crm_admin_email__nin=[None, ""],
            invitation_provisioning_id__ne=provisioning_id,
            invitation_status__in=[CRMAdminInvitationStatus.NOT_SENT.value, None],
        ).update_one(
            set__invitation_status=CRMAdminInvitationStatus.PENDING.value,
            set__invitation_provisioning_id=provisioning_id,
            set__invitation_attempts=0,
            unset__invitation_next_attempt_at=True,
            unset__invitation_last_error=True,
        )
        return bool(updated)

    @staticmethod
    def _claim(bot: Text, force: bool) -> Optional[CRMClientDetails]:
        now = datetime.utcnow()
        stale = now - timedelta(seconds=CLAIM_STALE_SECONDS)
        base = {"bot": bot, "onboarding_status": CRMOnboardingStatus.COMPLETED.value}
        from mongoengine.queryset.visitor import Q
        sendable = (
            Q(invitation_status__in=[CRMAdminInvitationStatus.PENDING.value, CRMAdminInvitationStatus.FAILED.value])
            & (Q(invitation_next_attempt_at__lte=now) | Q(invitation_next_attempt_at=None))
            & Q(invitation_attempts__lt=MAX_ATTEMPTS)
        ) | (Q(invitation_status=CRMAdminInvitationStatus.SENDING.value) & Q(invitation_claimed_at__lt=stale))
        if force:
            cooldown = now - timedelta(seconds=RESEND_COOLDOWN_SECONDS)
            sendable = (
                Q(invitation_status__in=[CRMAdminInvitationStatus.PENDING.value, CRMAdminInvitationStatus.FAILED.value,
                                         CRMAdminInvitationStatus.SENT.value])
                & (Q(invitation_last_attempt_at=None) | Q(invitation_last_attempt_at__lte=cooldown))
            ) | (Q(invitation_status=CRMAdminInvitationStatus.SENDING.value) & Q(invitation_claimed_at__lt=stale))
        claimed = CRMClientDetails.objects(Q(**base) & sendable).update_one(
            set__invitation_status=CRMAdminInvitationStatus.SENDING.value,
            set__invitation_claimed_at=now,
            set__invitation_last_attempt_at=now,
            inc__invitation_attempts=1,
        )
        if not claimed:
            return None
        return CRMClientDetails.objects(bot=bot).first()

    @staticmethod
    def build_email(company: Text, tenant_url: Text, setup_url: Text, administrator: bool = True):
        c, u, s = html.escape(company), html.escape(tenant_url), html.escape(setup_url)
        subject = f"Your {company} CRM is ready" if administrator else f"You have been invited to the {company} CRM"
        body = (
            f"<p>Hello,</p>"
            f"<p>The CRM for <b>{c}</b> has been set up and you have been "
            f"{'named its administrator' if administrator else 'given access to it'}.</p>"
            f"<p>CRM address: <a href=\"{u}\">{u}</a></p>"
            f"<p>To start, set your password using this one-time link, then sign in at the address above:</p>"
            f"<p><a href=\"{s}\">Set your password</a></p>"
            f"<p>The link works once and expires. If it has expired, ask your Kairon contact to resend the invitation. "
            f"No password has been sent to you; you choose your own.</p>"
            f"<p>If you were not expecting this message, you can ignore it.</p>"
        )
        return subject, body

    @staticmethod
    def _send_mail(email: Text, subject: Text, body: Text):
        if not Utility.email_conf["email"]["enable"]:
            raise AppException("Email delivery is not enabled (EMAIL_ENABLE).")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(MailUtility.trigger_smtp(email, subject, body, content_type="html"))
            return
        # Called from inside a running loop: run the coroutine on its own loop in a worker thread.
        errors = []

        def _run():
            try:
                asyncio.run(MailUtility.trigger_smtp(email, subject, body, content_type="html"))
            except Exception as e:  # surfaced below
                errors.append(e)
        t = threading.Thread(target=_run)
        t.start()
        t.join(60)
        if errors:
            raise errors[0]

    @classmethod
    def send(cls, bot: Text, force: bool = False) -> Dict:
        """One delivery attempt. Never raises for delivery problems: the outcome is recorded and returned."""
        doc = cls._claim(bot, force)
        if not doc:
            current = CRMClientDetails.objects(bot=bot).first()
            return {"attempted": False, "invitation_status": current.invitation_status if current else None}
        email = doc.crm_admin_email
        try:
            if not email:
                raise AppException("No CRM administrator email is configured for this tenant.")
            from kairon.crm.processor import CRMProcessor  # local import: the processor imports this module
            tenant_url = CRMProcessor.get_tenant_url(doc.site_name)
            allow_http = str(CRMProcessor._bench_config().get("sso_allow_insecure_http") or "").lower() in ("1", "true", "yes")
            if not tenant_url.startswith("https://") and not allow_http:
                raise AppException("Invitation not sent: the tenant URL is not HTTPS (set BENCH_TENANT_URL_SCHEME=https).")
            result = ConnectorUserClient(bot).call("resend_invitation", {"email": email, "purpose": "crm_admin"})
            path = ConnectorUserClient.validated_setup_path((result or {}).get("setup_path"))
            subject, body = cls.build_email(doc.company_name, tenant_url, tenant_url + path)
            cls._send_mail(email, subject, body)
        except Exception as e:
            attempts = doc.invitation_attempts
            delay = min(BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0)), BACKOFF_CAP_SECONDS)
            CRMClientDetails.objects(bot=bot).update_one(
                set__invitation_status=CRMAdminInvitationStatus.FAILED.value,
                set__invitation_last_error=_safe_error(e),
                set__invitation_next_attempt_at=datetime.utcnow() + timedelta(seconds=delay),
            )
            logger.warning(f"[CRMAdminInvitation] bot={bot} attempt={attempts} failed: {type(e).__name__}")
            return {"attempted": True, "invitation_status": CRMAdminInvitationStatus.FAILED.value, "attempts": attempts}
        CRMClientDetails.objects(bot=bot).update_one(
            set__invitation_status=CRMAdminInvitationStatus.SENT.value,
            set__invitation_sent_at=datetime.utcnow(),
            unset__invitation_last_error=True,
            unset__invitation_next_attempt_at=True,
        )
        logger.info(f"[CRMAdminInvitation] bot={bot} invitation delivered to provider")
        return {"attempted": True, "invitation_status": CRMAdminInvitationStatus.SENT.value, "attempts": doc.invitation_attempts}

    @classmethod
    def send_in_background(cls, bot: Text):
        """Fire-and-forget so the provisioning request is never held by SMTP or the connector."""
        threading.Thread(target=cls.send, args=(bot,), name=f"crm-invite-{bot}", daemon=True).start()

    @classmethod
    def retry_pending(cls, limit: int = 50) -> Dict:
        """Run by the scheduled job: delivers armed and failed-but-retryable invitations (bounded)."""
        from mongoengine.queryset.visitor import Q
        due = CRMClientDetails.objects(
            Q(onboarding_status=CRMOnboardingStatus.COMPLETED.value)
            & Q(invitation_status__in=[CRMAdminInvitationStatus.PENDING.value, CRMAdminInvitationStatus.FAILED.value,
                                       CRMAdminInvitationStatus.SENDING.value])
            & Q(invitation_attempts__lt=MAX_ATTEMPTS)
        ).limit(limit)
        summary = {"checked": 0, "sent": 0, "failed": 0, "skipped": 0}
        for doc in due:
            summary["checked"] += 1
            outcome = cls.send(doc.bot)
            if not outcome["attempted"]:
                summary["skipped"] += 1
            elif outcome["invitation_status"] == CRMAdminInvitationStatus.SENT.value:
                summary["sent"] += 1
            else:
                summary["failed"] += 1
        return summary
