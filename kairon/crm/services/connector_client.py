"""
Client for the tenant's `kairon_connector` user-management API (`kairon_connector.api.v1.users`).

Requests are signed with the tenant's lead-webhook secret (the same secret and HMAC scheme as events), so only Kairon can
call them and a captured request cannot be replayed or re-targeted. Which tenant is called is decided here from the
bot's own `CRMClientDetails`, never from request input.
"""
import re
from typing import Any, Dict, Optional, Text
from urllib.parse import urlparse, urlunparse

from kairon.crm.lead_dispatch import DEFAULT_BENCH_BASE_URL, get_lead_webhook_secret
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.events.publisher import KaironEventPublisher
from kairon.exceptions import AppException
from kairon.shared.utils import Utility

API_PREFIX = "/api/method/kairon_connector.api.v1.users."
OPERATIONS = ("list_users", "get_user", "invite_user", "resend_invitation", "set_user_enabled", "assignable_roles")
SETUP_LINK_PATTERN = re.compile(r"^/update-password\?key=[A-Za-z0-9_\-]{16,128}$")


class ConnectorUserClient:

    def __init__(self, bot: Text):
        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc:
            raise AppException("No CRM configuration found for this bot.")
        if doc.onboarding_status != CRMOnboardingStatus.COMPLETED.value or not doc.site_name:
            raise AppException("The CRM tenant is not ready yet.")
        self.bot = bot
        self.site_name = doc.site_name

    def _target(self, operation: Text) -> Text:
        if operation not in OPERATIONS:
            raise AppException("Unsupported user-management operation.")
        base_url = Utility.environment.get("crm", {}).get("bench", {}).get("base_url", DEFAULT_BENCH_BASE_URL)
        parsed = urlparse(base_url)
        netloc = f"{self.site_name}:{parsed.port}" if parsed.port else self.site_name
        return urlunparse((parsed.scheme, netloc, API_PREFIX + operation, "", "", ""))

    def call(self, operation: Text, body: Optional[Dict[Text, Any]] = None) -> Any:
        """Returns the connector's `message` payload. Raises AppException with a safe, specific message."""
        result = KaironEventPublisher.request_signed(
            self._target(operation), get_lead_webhook_secret(self.bot), {"site": self.site_name, **(body or {})}
        )
        data = result.get("json") or {}
        if not result["success"]:
            status = result["status_code"]
            detail = data.get("error") if isinstance(data, dict) and isinstance(data.get("error"), str) else None
            if status in (401, 403):
                raise AppException("The CRM tenant rejected the request (authentication failed).")
            if detail:
                raise AppException(detail[:300])
            raise AppException(f"The CRM tenant could not complete the request (HTTP {status}).")
        return data.get("message") if isinstance(data, dict) else None

    @staticmethod
    def validated_setup_path(path: Any) -> Text:
        """The setup link must be the tenant's own password-setup page; nothing else is ever emailed."""
        if not isinstance(path, str) or not SETUP_LINK_PATTERN.match(path):
            raise AppException("The CRM tenant returned an invalid setup link.")
        return path
