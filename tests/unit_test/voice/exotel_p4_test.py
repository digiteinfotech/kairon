from unittest.mock import MagicMock, patch

import pytest

from kairon.exceptions import AppException
from kairon.shared.voice.exotel.outbound import ExotelOutboundClient
from kairon.shared.voice.factory import VoiceOutboundFactory


class TestExotelOutboundClient:

    def _client(self):
        return ExotelOutboundClient.from_config({
            "account_sid": "AC1", "api_key": "K1", "api_token": "T1",
            "subdomain": "api.in.exotel.com", "phone_number": "08047000000",
        })

    def test_from_config_maps_fields(self):
        c = self._client()
        assert c.api_key == "K1" and c.api_token == "T1"
        assert c.subdomain == "api.in.exotel.com" and c.from_number == "08047000000"

    def test_defaults_fall_back(self):
        c = ExotelOutboundClient(account_sid="ACX", auth_token="TX", from_number="0800")
        assert c.api_key == "ACX" and c.api_token == "TX"
        assert c.from_number == "0800" and c.subdomain == "api.exotel.com"

    def test_connect_url_and_flow_url(self):
        c = self._client()
        assert c._connect_url() == "https://api.in.exotel.com/v1/Accounts/AC1/Calls/connect.json"
        assert c.flow_app_url("999") == "http://my.exotel.com/AC1/exoml/start_voice/999"

    def test_parse_call_sid_shapes(self):
        assert ExotelOutboundClient._parse_call_sid({"Call": {"Sid": "CS9"}}) == "CS9"
        assert ExotelOutboundClient._parse_call_sid({"Sid": "CS8"}) == "CS8"
        assert ExotelOutboundClient._parse_call_sid({}) == ""
        assert ExotelOutboundClient._parse_call_sid(None) == ""

    def test_initiate_call_posts_expected_payload(self):
        c = self._client()
        resp = MagicMock()
        resp.json.return_value = {"Call": {"Sid": "CALL123", "Status": "in-progress"}}
        resp.raise_for_status.return_value = None
        with patch("requests.post", return_value=resp) as mock_post:
            sid = c.initiate_call("+919999", "http://flow", status_callback_url="http://cb")
        assert sid == "CALL123"
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.in.exotel.com/v1/Accounts/AC1/Calls/connect.json"
        assert kwargs["auth"] == ("K1", "T1")
        assert kwargs["data"] == {
            "From": "+919999", "CallerId": "08047000000", "Url": "http://flow",
            "StatusCallback": "http://cb", "StatusCallbackMethod": "POST",
        }
        assert kwargs["timeout"] == 30

    def test_connect_to_flow_uses_app_url(self):
        c = self._client()
        resp = MagicMock()
        resp.json.return_value = {"Call": {"Sid": "CALL9"}}
        resp.raise_for_status.return_value = None
        with patch("requests.post", return_value=resp) as mock_post:
            c.connect_to_flow("+918888", "555")
        assert mock_post.call_args.kwargs["data"]["Url"] == (
            "http://my.exotel.com/AC1/exoml/start_voice/555"
        )

    def test_missing_sid_raises(self):
        c = self._client()
        resp = MagicMock()
        resp.json.return_value = {"Call": {}}
        resp.raise_for_status.return_value = None
        with patch("requests.post", return_value=resp):
            with pytest.raises(AppException, match="no Sid"):
                c.initiate_call("+91", "http://flow")

    def test_network_error_raises_appexception(self):
        c = self._client()
        with patch("requests.post", side_effect=ConnectionError("down")):
            with pytest.raises(AppException, match="Exotel outbound call failed"):
                c.initiate_call("+91", "http://flow")

    def test_url_never_contains_credentials(self):
        c = self._client()
        assert "K1" not in c._connect_url() and "T1" not in c._connect_url() and "@" not in c._connect_url()
        assert "K1" not in c.flow_app_url("1") and "T1" not in c.flow_app_url("1")

    def test_http_error_message_has_status_but_no_credentials_or_url(self):
        import requests
        c = self._client()
        resp = MagicMock(status_code=401, reason="Unauthorized")
        err = requests.exceptions.HTTPError("401 Client Error: Unauthorized for url: https://K1:T1@api/x", response=resp)
        bad = MagicMock()
        bad.raise_for_status.side_effect = err
        with patch("requests.post", return_value=bad):
            with pytest.raises(AppException) as ei:
                c.initiate_call("+91", "http://flow")
        msg = str(ei.value)
        assert "HTTP 401 Unauthorized" in msg
        assert "K1" not in msg and "T1" not in msg and "http" not in msg
        assert ei.value.__cause__ is None

    def test_other_errors_are_scrubbed_of_credentials(self):
        c = self._client()
        with patch("requests.post", side_effect=RuntimeError("failed calling https://K1:T1@host with key K1 token T1")):
            with pytest.raises(AppException) as ei:
                c.initiate_call("+91", "http://flow")
        msg = str(ei.value)
        assert "K1" not in msg and "T1" not in msg and "***" in msg
        assert ei.value.__cause__ is None


class TestVoiceOutboundFactory:

    def test_exotel_registered(self):
        assert VoiceOutboundFactory.get_client("exotel") is ExotelOutboundClient

    def test_twilio_still_registered(self):
        from kairon.shared.voice.twilio import TwilioOutboundClient
        assert VoiceOutboundFactory.get_client("twilio") is TwilioOutboundClient

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            VoiceOutboundFactory.get_client("vonage")
