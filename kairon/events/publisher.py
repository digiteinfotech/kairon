import uuid
import datetime
import time
import hmac
import hashlib
import json
import requests
from typing import Dict, Any, Optional
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
    def calculate_signature(secret: str, timestamp: str, body_bytes: bytes, bound_id: Optional[str] = None) -> str:
        """
        Calculates HMAC-SHA256 signature over a timestamp-bound payload, so the
        X-Kairon-Timestamp header cannot be swapped on a captured request without
        invalidating the signature (signed_payload = "<timestamp>." + raw body bytes).
        With `bound_id` the request id is signed too ("<timestamp>.<bound_id>." + body), so the receiver's replay check on
        that id cannot be sidestepped by putting a fresh id on a captured request.
        """
        prefix = f"{timestamp}.{bound_id}." if bound_id else f"{timestamp}."
        signed_payload = prefix.encode('utf-8') + body_bytes
        return hmac.new(secret.encode('utf-8'), signed_payload, hashlib.sha256).hexdigest()

    @staticmethod
    def _post(target_url: str, body_bytes: bytes, headers: Dict[str, str], timeout_seconds: int,
              host_header: Optional[str] = None):
        """
        POSTs the signed body. With `host_header` the request goes to `target_url` (the shared Bench frontend) and is
        routed to that tenant by `Host`, exactly as ERPNextClient reaches it, instead of resolving the tenant's name.
        """
        if host_header:
            from kairon.crm.services.bench_http import build_bench_session
            return build_bench_session(host_header).post(
                target_url, data=body_bytes, headers=headers, timeout=timeout_seconds)
        return requests.post(target_url, data=body_bytes, headers=headers, timeout=timeout_seconds)

    @classmethod
    def publish_webhook(
        cls,
        target_url: str,
        secret: str,
        event: KaironEvent,
        timeout_seconds: int = 10,
        host_header: Optional[str] = None,
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
            response = cls._post(target_url, body_bytes, headers, timeout_seconds, host_header)
            logger.info(f"[KaironEventPublisher] Dispatched {event.event_type} ({event.event_id}) -> Status {response.status_code}")
            return {
                "status_code": response.status_code,
                "response_text": response.text,
                "success": response.status_code in (200, 201, 202)
            }
        except Exception as e:
            # Log the class only: the exception text can echo the URL.
            logger.error(f"[KaironEventPublisher] Failed to dispatch event {event.event_id}: {type(e).__name__}")
            raise AppException(f"Webhook dispatch failed: {type(e).__name__}")

    @classmethod
    def request_signed(
        cls,
        target_url: str,
        secret: str,
        body: Dict[str, Any],
        timeout_seconds: int = 15,
        host_header: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Signed request/response call (same timestamp-bound HMAC scheme as `publish_webhook`, with the request id signed as
        well) for connector endpoints that return data, such as user management. `X-Kairon-Event-ID` is a fresh single-use
        value the receiver records to reject replays within the signature window; being part of the signature, it cannot be
        replaced on a captured request. The receiver (kairon_connector) must verify with the same id-bound scheme.
        Returns status code and parsed JSON.
        """
        body_bytes = json.dumps(body, separators=(',', ':')).encode('utf-8')
        timestamp = str(int(time.time()))
        request_id = f"req_{uuid.uuid4().hex}"
        headers = {
            "Content-Type": "application/json",
            "X-Kairon-Signature": f"sha256={cls.calculate_signature(secret, timestamp, body_bytes, bound_id=request_id)}",
            "X-Kairon-Timestamp": timestamp,
            "X-Kairon-Event-ID": request_id,
        }
        try:
            response = cls._post(target_url, body_bytes, headers, timeout_seconds, host_header)
        except requests.RequestException as e:
            # Log the class only: the exception text can echo the URL.
            logger.error(f"[KaironEventPublisher] Signed request {request_id} failed: {type(e).__name__}")
            raise AppException(f"Connector request failed: {type(e).__name__}")
        try:
            data = response.json()
        except ValueError:
            data = None
        return {"status_code": response.status_code, "json": data, "success": response.status_code == 200}
