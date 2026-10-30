"""
Tenant user management for Kairon staff, executed by the tenant's own `kairon_connector` (never directly against
ERPNext's database and never with Administrator credentials). Kairon validates, authorises (route layer), audits and
sends the invitation email; the connector enforces the same role allowlist and tenant isolation on its side.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Text

from loguru import logger

from kairon.crm.constants import ASSIGNABLE_USER_ROLES
from kairon.crm.models import CRMClientDetails, CRMInvitation, CRMInvitationStatus
from kairon.crm.schemas import validate_email_address
from kairon.crm.services.admin_invitation import CRMAdminInvitationService, _safe_error
from kairon.crm.services.connector_client import ConnectorUserClient
from kairon.exceptions import AppException

RESEND_COOLDOWN_SECONDS = 60
MAX_ROLES_PER_USER = 5
PROTECTED_USERS = ("administrator", "guest")


class CRMUserManagement:

    @staticmethod
    def _email(email: Text) -> Text:
        try:
            clean = validate_email_address(email)
        except ValueError as e:
            raise AppException(str(e))
        if clean in PROTECTED_USERS or clean.startswith("kairon-crm@"):
            raise AppException("This account cannot be managed here.")
        return clean

    @staticmethod
    def validate_roles(roles: Optional[List[Text]]) -> List[Text]:
        cleaned: List[Text] = []
        for role in roles or []:
            role = (role or "").strip()
            if role and role not in cleaned:
                cleaned.append(role)
        if not cleaned:
            raise AppException("At least one role is required.")
        if len(cleaned) > MAX_ROLES_PER_USER:
            raise AppException(f"At most {MAX_ROLES_PER_USER} roles can be assigned at once.")
        invalid = [r for r in cleaned if r not in ASSIGNABLE_USER_ROLES]
        if invalid:
            raise AppException(f"Role(s) not permitted: {', '.join(invalid)}.")
        return cleaned

    @staticmethod
    def assignable_roles() -> List[Text]:
        return list(ASSIGNABLE_USER_ROLES)

    @staticmethod
    def list_users(bot: Text) -> List[Dict]:
        users = ConnectorUserClient(bot).call("list_users") or []
        return users if isinstance(users, list) else []

    @staticmethod
    def get_user(bot: Text, email: Text) -> Dict:
        return ConnectorUserClient(bot).call("get_user", {"email": CRMUserManagement._email(email)}) or {}

    @classmethod
    def invite_user(cls, bot: Text, actor: Text, email: Text, roles: List[Text], first_name: Optional[Text] = None) -> Dict:
        email = cls._email(email)
        roles = cls.validate_roles(roles)
        doc = CRMClientDetails.objects(bot=bot).first()
        client = ConnectorUserClient(bot)  # also enforces "tenant is ready"
        result = client.call("invite_user", {"email": email, "roles": roles, "first_name": (first_name or "").strip()[:60]}) or {}
        status = result.get("status")
        if status not in ("invited", "already_exists"):
            raise AppException("The CRM tenant returned an unexpected response.")
        if status == "already_exists":
            # Never silently re-grant roles to, or re-invite, an existing account.
            raise AppException(f"A user with the email '{email}' already exists in this CRM.")
        record = CRMInvitation(
            bot=bot, user=actor, site_name=doc.site_name, company=doc.erpnext_company or doc.company_name,
            email=email, roles=roles, invitation_status=CRMInvitationStatus.PENDING.value, invited_at=datetime.utcnow(),
        ).save()
        delivery = cls._deliver(doc, email, result.get("setup_path"), record)
        return {"email": email, "roles": roles, "status": "invited", "email_delivery": delivery}

    @classmethod
    def resend_invitation(cls, bot: Text, actor: Text, email: Text) -> Dict:
        email = cls._email(email)
        doc = CRMClientDetails.objects(bot=bot).first()
        record = CRMInvitation.objects(bot=bot, email=email).order_by("-invited_at").first()
        if record and record.invited_at and datetime.utcnow() - record.invited_at < timedelta(seconds=RESEND_COOLDOWN_SECONDS):
            raise AppException(f"Please wait {RESEND_COOLDOWN_SECONDS} seconds before resending.")
        result = ConnectorUserClient(bot).call("resend_invitation", {"email": email, "purpose": "user"}) or {}
        if not record:
            record = CRMInvitation(bot=bot, user=actor, site_name=doc.site_name,
                                   company=doc.erpnext_company or doc.company_name, email=email)
        record.invited_at = datetime.utcnow()
        record.invitation_status = CRMInvitationStatus.PENDING.value
        record.save()
        return {"email": email, "email_delivery": cls._deliver(doc, email, result.get("setup_path"), record)}

    @staticmethod
    def set_enabled(bot: Text, actor: Text, email: Text, enabled: bool) -> Dict:
        email = CRMUserManagement._email(email)
        owner = CRMClientDetails.objects(bot=bot).first()
        if not enabled and owner and email == (owner.crm_admin_email or "").lower():
            raise AppException("The CRM administrator cannot be disabled here.")
        result = ConnectorUserClient(bot).call("set_user_enabled", {"email": email, "enabled": bool(enabled)})
        logger.info(f"[CRMUserManagement] bot={bot} actor={actor} {'enabled' if enabled else 'disabled'} user")
        return result or {"email": email, "enabled": bool(enabled)}

    @staticmethod
    def _deliver(doc: CRMClientDetails, email: Text, setup_path, record: CRMInvitation) -> Text:
        """Sends the setup link; returns 'sent' or 'failed' and records the outcome without the link."""
        from kairon.crm.processor import CRMProcessor
        try:
            path = ConnectorUserClient.validated_setup_path(setup_path)
            tenant_url = CRMProcessor.get_tenant_url(doc.site_name)
            allow_http = str(CRMProcessor._bench_config().get("sso_allow_insecure_http") or "").lower() in ("1", "true", "yes")
            if not tenant_url.startswith("https://") and not allow_http:
                raise AppException("Invitation not sent: the tenant URL is not HTTPS.")
            subject, body = CRMAdminInvitationService.build_email(doc.company_name, tenant_url, tenant_url + path, administrator=False)
            CRMAdminInvitationService._send_mail(email, subject, body)
            record.last_error = None
            record.save()
            return "sent"
        except Exception as e:
            record.last_error = _safe_error(e)
            record.save()
            return "failed"
