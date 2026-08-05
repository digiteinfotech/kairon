from unittest.mock import MagicMock, patch

import pytest

from kairon.exceptions import AppException
from kairon.shared.voice.exotel.outbound import ExotelOutboundClient
from kairon.shared.voice.factory import VoiceOutboundFactory


class TestExotelOutboundClient:

    def _client(self):
        return ExotelOutboundClient.from_config({
            "account_sid": "AC1", "api_key": "K1", "api_token": "T1",
            "subdomain": "api.in.exotel.com", "exophone": "08047000000",
        })

    def test_from_config_maps_fields(self):
        c = self._client()
        assert c.api_key == "K1" and c.api_token == "T1"
        assert c.subdomain == "api.in.exotel.com" and c.exophone == "08047000000"

    def test_defaults_fall_back(self):
        c = ExotelOutboundClient(account_sid="ACX", auth_token="TX", from_number="0800")
        assert c.api_key == "ACX" and c.api_token == "TX"
        assert c.exophone == "0800" and c.subdomain == "api.exotel.com"

    def test_connect_url_and_flow_url(self):
        c = self._client()
        assert c._connect_url() == (
            "https://K1:T1@api.in.exotel.com/v1/Accounts/AC1/Calls/connect.json"
        )
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
        assert args[0] == "https://K1:T1@api.in.exotel.com/v1/Accounts/AC1/Calls/connect.json"
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


class TestVoiceOutboundFactory:

    def test_exotel_registered(self):
        assert VoiceOutboundFactory.get_client("exotel") is ExotelOutboundClient

    def test_twilio_still_registered(self):
        from kairon.shared.voice.twilio import TwilioOutboundClient
        assert VoiceOutboundFactory.get_client("twilio") is TwilioOutboundClient

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            VoiceOutboundFactory.get_client("vonage")
