import json
import uuid
from typing import Optional

from loguru import logger

from kairon.events.publisher import KaironEvent, KaironEventPublisher
from kairon.shared.utils import Utility

CRM_ENABLED = "crm.enabled"
CRM_DISABLED = "crm.disabled"
CRM_TENANT_PROVISIONED = "crm.tenant.provisioned"
CRM_TENANT_PROVISION_FAILED = "crm.tenant.provision_failed"

EVENTS_PATH = "/api/crm/events"
TIMEOUT_SECONDS = 5


class CRMMeteringSync:
    """
    Hands CRM metadata to Kairon Metering over its signed HTTP API, using the existing KaironEvent
    envelope and KaironEventPublisher signing. Kairon stays the authoritative source of CRM state:
    this is a best-effort notification. A Metering outage or rejection is logged and reported to the
    caller but never raises, so it can never break onboarding or settings updates. Payloads carry
    metadata only (no passwords, keys, secrets or error text).
    """

    @staticmethod
    def is_configured() -> bool:
        url, secret = CRMMeteringSync._config()
        return bool(url and secret)

    @staticmethod
    def _config():
        config = (Utility.environment.get("crm") or {}).get("metering") or {}
        return config.get("url"), config.get("event_secret")

    @staticmethod
    def publish(event_type: str, payload: dict, event_id: Optional[str] = None,
                correlation_id: Optional[str] = None) -> dict:
        """
        Returns {"sent": bool, "event_id": str, "reason": str|None}. `sent` is True only when Metering
        answered success (Metering replies HTTP 200 with success=false for rejections, so the body is
        checked). Re-sending the same `event_id` is safe: Metering ignores duplicates.
        """
        url, secret = CRMMeteringSync._config()
        event_id = event_id or f"evt_{uuid.uuid4().hex}"
        if not (url and secret):
            logger.debug("[CRMMeteringSync] Metering not configured; skipping {} ({})", event_type, event_id)
            return {"sent": False, "event_id": event_id, "reason": "not_configured"}
        event = KaironEvent(event_type=event_type, payload=payload, event_id=event_id)
        if correlation_id:
            event.correlation_id = correlation_id
        try:
            result = KaironEventPublisher.publish_webhook(
                f"{url.rstrip('/')}{EVENTS_PATH}", secret, event, timeout_seconds=TIMEOUT_SECONDS
            )
            body = json.loads(result.get("response_text") or "{}")
            if result.get("success") and body.get("success") is True:
                return {"sent": True, "event_id": event_id, "reason": None}
            reason = f"rejected (HTTP {result.get('status_code')}, error_code {body.get('error_code')})"
        except Exception as e:  # network error, timeout, non-JSON reply
            reason = f"unreachable ({type(e).__name__})"
        logger.warning("[CRMMeteringSync] {} {} not delivered: {}", event_type, event_id, reason)
        return {"sent": False, "event_id": event_id, "reason": reason}

    @staticmethod
    def publish_bot_state(bot: str, user: str, enabled: bool) -> dict:
        return CRMMeteringSync.publish(
            CRM_ENABLED if enabled else CRM_DISABLED, {"bot": bot, "user": user}
        )
