"""
Resolves where, and with which secret, the bot runtime sends `lead.qualified` events.

Kept separate from `kairon.crm.processor` on purpose: the action server loads this module for every conversation,
and the processor pulls in the provisioning stack (ERPNext client, Docker/Bench executor). This module may only
depend on the CRM models and shared utilities.
"""
from typing import Text, Tuple

from kairon.crm.models import CRMClientDetails
from kairon.exceptions import AppException
from kairon.shared.utils import Utility

WEBHOOK_PATH = "/api/method/kairon_connector.api.v1.webhook.receive_event"
DEFAULT_BENCH_BASE_URL = "http://localhost:8080"


def build_target_url(base_url: Text, path: Text = WEBHOOK_PATH) -> Text:
    """
    Endpoint on the shared Bench frontend. The tenant is chosen by the `Host` header (pass the site name as
    `host_header` to `KaironEventPublisher`), the same way ERPNextClient reaches it, so nothing needs to resolve the
    tenant's own hostname from the action server.
    """
    return base_url.rstrip("/") + path


def get_lead_webhook_secret(bot: Text) -> Text:
    """Decrypted per-tenant secret used to sign outbound Kairon events for this bot's tenant. Never log it."""
    doc = CRMClientDetails.objects(bot=bot).first()
    if not doc or not doc.lead_webhook_secret:
        raise AppException("Lead webhook secret not configured for this bot. Is provisioning COMPLETED?")
    return Utility.decrypt_message(doc.lead_webhook_secret)


def bench_base_url() -> Text:
    return Utility.environment.get("crm", {}).get("bench", {}).get("base_url", DEFAULT_BENCH_BASE_URL)


def resolve_lead_target(bot: Text) -> Tuple[Text, Text]:
    """Returns (webhook URL on the Bench frontend, signing secret) for the bot's tenant. Send with `host_header=site_name`."""
    return build_target_url(bench_base_url()), get_lead_webhook_secret(bot)
