import uuid
import datetime
import time
import hmac
import hashlib
import json
import requests
from typing import Dict, Any
from dataclasses import dataclass, field
from loguru import logger
from kairon.exceptions import AppException


@dataclass
class KaironEvent:
    """
    Standardized typed integration event model for Kairon external dispatches.
    """
    event_type: str
    payload: Dict[str, Any]
    event_version: str = "1.0"
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    correlation_id: str = field(default_factory=lambda: f"corr_{uuid.uuid4().hex}")
    timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "event_version": self.event_version,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "payload": self.payload
        }


class KaironEventPublisher:
    """
    Publishes Kairon integration events to external webhook receivers (e.g. Frappe CRM).
    Handles HMAC-SHA256 signature generation, timestamp headers, and HTTP dispatches.
    """

    @staticmethod
    def calculate_signature(secret: str, timestamp: str, body_bytes: bytes) -> str:
        """
        Calculates HMAC-SHA256 signature over a timestamp-bound payload, so the
        X-Kairon-Timestamp header cannot be swapped on a captured request without
        invalidating the signature (signed_payload = "<timestamp>." + raw body bytes).
        """
        signed_payload = f"{timestamp}.".encode('utf-8') + body_bytes
        return hmac.new(secret.encode('utf-8'), signed_payload, hashlib.sha256).hexdigest()

    @classmethod
    def publish_webhook(
        cls,
        target_url: str,
        secret: str,
        event: KaironEvent,
        timeout_seconds: int = 10
    ) -> Dict[str, Any]:
        """
        Dispatches a KaironEvent payload to a webhook URL with a timestamp-bound HMAC signature.
        """
        payload_dict = event.to_dict()
        body_bytes = json.dumps(payload_dict, separators=(',', ':')).encode('utf-8')
        timestamp = str(int(time.time()))
        signature = cls.calculate_signature(secret, timestamp, body_bytes)

        headers = {
            "Content-Type": "application/json",
            "X-Kairon-Signature": f"sha256={signature}",
            "X-Kairon-Timestamp": timestamp,
            "X-Kairon-Event-ID": event.event_id,
            "X-Correlation-ID": event.correlation_id
        }

        try:
            response = requests.post(
                target_url,
                data=body_bytes,
                headers=headers,
                timeout=timeout_seconds
            )
            logger.info(f"[KaironEventPublisher] Dispatched {event.event_type} ({event.event_id}) to {target_url} -> Status {response.status_code}")
            return {
                "status_code": response.status_code,
                "response_text": response.text,
                "success": response.status_code in (200, 201, 202)
            }
        except Exception as e:
            logger.error(f"[KaironEventPublisher] Failed to dispatch event {event.event_id} to {target_url}: {e}")
            raise AppException(f"Webhook dispatch failed: {str(e)}")
