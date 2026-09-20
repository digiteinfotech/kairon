import json
import pytest
from unittest.mock import patch, MagicMock
from kairon.events.publisher import KaironEvent, KaironEventPublisher


def test_kairon_event_serialization():
    event = KaironEvent(
        event_type="lead.qualified",
        payload={"name": "Alice", "email": "alice@example.com"}
    )
    event_dict = event.to_dict()

    assert event_dict["event_type"] == "lead.qualified"
    assert event_dict["event_version"] == "1.0"
    assert event_dict["event_id"].startswith("evt_")
    assert event_dict["correlation_id"].startswith("corr_")
    assert "timestamp" in event_dict
    assert event_dict["payload"]["name"] == "Alice"


def test_hmac_signature_calculation():
    secret = "my_secret_key_123"
    timestamp = "1700000000"
    payload_bytes = b'{"event_type":"lead.qualified"}'

    signature = KaironEventPublisher.calculate_signature(secret, timestamp, payload_bytes)
    assert isinstance(signature, str)
    assert len(signature) == 64  # SHA-256 hex string length


def test_hmac_signature_is_timestamp_bound():
    """A different timestamp over the same body must produce a different signature,
    so a captured (signature, body) pair can't be replayed under a forged timestamp."""
    secret = "my_secret_key_123"
    payload_bytes = b'{"event_type":"lead.qualified"}'

    sig_a = KaironEventPublisher.calculate_signature(secret, "1700000000", payload_bytes)
    sig_b = KaironEventPublisher.calculate_signature(secret, "1700000050", payload_bytes)
    assert sig_a != sig_b


@patch("requests.post")
def test_publish_webhook_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.text = json.dumps({"status": "queued", "event_id": "evt_123"})
    mock_post.return_value = mock_response

    event = KaironEvent(
        event_type="lead.qualified",
        payload={"name": "Bob", "email": "bob@example.com"}
    )
    target_url = "https://tenant1.crm.domain.com/api/method/kairon_connector.api.v1.webhook.receive_event"
    secret = "tenant_secret_xyz"

    result = KaironEventPublisher.publish_webhook(target_url, secret, event)

    assert result["success"] is True
    assert result["status_code"] == 202
    mock_post.assert_called_once()

    call_args = mock_post.call_args
    headers = call_args[1]["headers"]
    assert "X-Kairon-Signature" in headers
    assert headers["X-Kairon-Signature"].startswith("sha256=")
    assert "X-Kairon-Timestamp" in headers
    assert headers["X-Kairon-Event-ID"] == event.event_id
    assert headers["X-Correlation-ID"] == event.correlation_id
