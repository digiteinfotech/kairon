"""
Resolves where, and with which secret, the bot runtime sends `lead.qualified` events.

Kept separate from `kairon.crm.processor` on purpose: the action server loads this module for every conversation,
and the processor pulls in the provisioning stack (ERPNext client, Docker/Bench executor). This module may only
depend on the CRM models and shared utilities.
"""
from typing import Text, Tuple
from urllib.parse import urlparse, urlunparse

from kairon.crm.models import CRMClientDetails
from kairon.exceptions import AppException
from kairon.shared.utils import Utility

WEBHOOK_PATH = "/api/method/kairon_connector.api.v1.webhook.receive_event"
DEFAULT_BENCH_BASE_URL = "http://localhost:8080"


def build_target_url(base_url: Text, site_name: Text) -> Text:
    """Routes to the right ERPNext tenant the same way ERPNextClient does (Host-derived from the URL itself),
    by substituting the site's hostname into the shared bench base_url."""
    parsed = urlparse(base_url)
    netloc = f"{site_name}:{parsed.port}" if parsed.port else site_name
    return urlunparse((parsed.scheme, netloc, WEBHOOK_PATH, "", "", ""))


def get_lead_webhook_secret(bot: Text) -> Text:
    """Decrypted per-tenant secret used to sign outbound Kairon events for this bot's tenant. Never log it."""
    doc = CRMClientDetails.objects(bot=bot).first()
    if not doc or not doc.lead_webhook_secret:
        raise AppException("Lead webhook secret not configured for this bot. Is provisioning COMPLETED?")
    return Utility.decrypt_message(doc.lead_webhook_secret)


def resolve_lead_target(bot: Text, site_name: Text) -> Tuple[Text, Text]:
    """Returns (webhook URL, signing secret) for the bot's tenant `site_name`."""
    base_url = Utility.environment.get("crm", {}).get("bench", {}).get("base_url", DEFAULT_BENCH_BASE_URL)
    return build_target_url(base_url, site_name), get_lead_webhook_secret(bot)
