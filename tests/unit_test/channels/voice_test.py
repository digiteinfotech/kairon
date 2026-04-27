import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mongoengine import connect, disconnect
from mongoengine.errors import DoesNotExist
from starlette.testclient import TestClient

from kairon.exceptions import AppException
from kairon.shared.utils import Utility


class TestVoiceProviderFactory:

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()

    def test_get_provider_twilio(self):
        from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory
        from kairon.chat.handlers.channels.clients.voice.twilio import TwilioVoiceProvider

        cls = VoiceProviderFactory.get_provider("twilio")
        assert cls is TwilioVoiceProvider

    def test_get_provider_unknown_raises(self):
        from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory

        with pytest.raises(AppException, match="not implemented"):
            VoiceProviderFactory.get_provider("vonage")

    def test_get_provider_empty_string_raises(self):
        from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory

        with pytest.raises(AppException):
            VoiceProviderFactory.get_provider("")


class TestTwilioVoiceProvider:

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))

    def _make_config(self, extra=None):
        config = {
            "account_sid": Utility.encrypt_message("ACtest1234567890"),
            "auth_token": Utility.encrypt_message("test_auth_token"),
            "phone_number": "+12025551234",
            "telephony_provider": "twilio",
            "voice_type": "Polly.Amy",
            "voice_types": ["Polly.Amy", "Polly.Matthew"],
            "process_url": "https://agent.kairon.io/api/bot/testbot/channel/voice/twilio/process/TOKEN",
            "call_url": "https://agent.kairon.io/api/bot/testbot/channel/voice/twilio/call/TOKEN",
            "status_url": "https://agent.kairon.io/api/bot/testbot/channel/voice/twilio/call/status/TOKEN",
        }
        if extra:
            config.update(extra)
        return config

    def _make_provider(self, extra=None):
        from kairon.chat.handlers.channels.clients.voice.twilio import TwilioVoiceProvider
        return TwilioVoiceProvider("testbot", self._make_config(extra))

    def test_init_decrypts_credentials(self):
        provider = self._make_provider()
        assert provider.account_sid == "ACtest1234567890"
        assert provider.auth_token == "test_auth_token"
        assert provider.phone_number == "+12025551234"
        assert provider.voice_type == "Polly.Amy"
        assert "Polly.Amy" in provider.voice_types

    def test_validate_signature_valid(self):
        provider = self._make_provider()
        request = MagicMock()
        request.headers = {"X-Twilio-Signature": "valid_sig"}
        with patch.object(provider._validator, "validate", return_value=True) as mock_validate:
            result = provider.validate_signature(
                request, "https://example.com/call", {"CallSid": "CA123"}
            )
        assert result is True
        mock_validate.assert_called_once_with(
            "https://example.com/call", {"CallSid": "CA123"}, "valid_sig"
        )

    def test_validate_signature_invalid(self):
        provider = self._make_provider()
        request = MagicMock()
        request.headers = {"X-Twilio-Signature": "bad_sig"}
        with patch.object(provider._validator, "validate", return_value=False):
            result = provider.validate_signature(request, "https://example.com/call", {})
        assert result is False

    def test_validate_signature_missing_header(self):
        provider = self._make_provider()
        request = MagicMock()
        request.headers = {}
        with patch.object(provider._validator, "validate", return_value=False) as mock_validate:
            provider.validate_signature(request, "https://example.com/call", {})
        mock_validate.assert_called_once_with("https://example.com/call", {}, "")

    @pytest.mark.asyncio
    async def test_handle_incoming_call_returns_twiml_with_gather(self):
        provider = self._make_provider()
        request = MagicMock()
        twiml = await provider.handle_incoming_call(request)
        assert "<Gather" in twiml
        assert "action=" in twiml
        assert provider.process_url in twiml
        assert "<Say" in twiml
        assert "Hello" in twiml

    @pytest.mark.asyncio
    async def test_handle_incoming_call_uses_custom_welcome_message(self):
        provider = self._make_provider(extra={"welcomeMessage": "Howdy partner!"})
        request = MagicMock()
        twiml = await provider.handle_incoming_call(request)
        assert "Howdy partner!" in twiml

    @pytest.mark.asyncio
    async def test_handle_incoming_call_uses_voice_type(self):
        provider = self._make_provider(extra={"voice_type": "Polly.Matthew"})
        request = MagicMock()
        twiml = await provider.handle_incoming_call(request)
        assert "Polly.Matthew" in twiml

    @pytest.mark.asyncio
    async def test_handle_call_processing_with_rasa_response(self):
        provider = self._make_provider()
        request = MagicMock()
        twiml = await provider.handle_call_processing(request, "testbot", "Your order is confirmed.")
        assert "<Say" in twiml
        assert "Your order is confirmed." in twiml
        assert "<Gather" in twiml
        assert provider.process_url in twiml

    @pytest.mark.asyncio
    async def test_handle_call_processing_empty_response_still_valid(self):
        provider = self._make_provider()
        request = MagicMock()
        twiml = await provider.handle_call_processing(request, "testbot", "")
        assert "<Response>" in twiml or "<?xml" in twiml
        assert "<Gather" in twiml

    @pytest.mark.asyncio
    async def test_handle_call_status_saves_channel_log(self):
        provider = self._make_provider()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallStatus": "completed",
            "CallSid": "CAtest123",
            "CallDuration": "42",
        })
        with patch("kairon.chat.handlers.channels.clients.voice.twilio.ChannelLogs") as mock_logs:
            mock_instance = MagicMock()
            mock_logs.return_value = mock_instance
            await provider.handle_call_status(request, "testbot")
        mock_logs.assert_called_once()
        call_kwargs = mock_logs.call_args[1]
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["message_id"] == "CAtest123"
        assert call_kwargs["bot"] == "testbot"
        mock_instance.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_call_status_unknown_status(self):
        provider = self._make_provider()
        request = MagicMock()
        request.form = AsyncMock(return_value={})
        with patch("kairon.chat.handlers.channels.clients.voice.twilio.ChannelLogs") as mock_logs:
            mock_instance = MagicMock()
            mock_logs.return_value = mock_instance
            await provider.handle_call_status(request, "testbot")
        call_kwargs = mock_logs.call_args[1]
        assert call_kwargs["status"] == "unknown"
        assert call_kwargs["message_id"] == "unknown"

    def test_validate_config_passes_with_all_required_fields(self):
        from kairon.chat.handlers.channels.clients.voice.twilio import TwilioVoiceProvider
        provider = self._make_provider()
        provider.validate_config({
            "account_sid": "ACxx",
            "auth_token": "auth",
            "phone_number": "+1xx",
        })

    def test_validate_config_missing_account_sid_raises(self):
        provider = self._make_provider()
        with pytest.raises(AppException, match="account_sid"):
            provider.validate_config({"auth_token": "x", "phone_number": "+1"})

    def test_validate_config_missing_auth_token_raises(self):
        provider = self._make_provider()
        with pytest.raises(AppException, match="auth_token"):
            provider.validate_config({"account_sid": "x", "phone_number": "+1"})

    def test_validate_config_missing_phone_number_raises(self):
        provider = self._make_provider()
        with pytest.raises(AppException, match="phone_number"):
            provider.validate_config({"account_sid": "x", "auth_token": "y"})


class TestVoiceOutput:

    @pytest.mark.asyncio
    async def test_send_text_message_accumulates(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_text_message("user1", "Hello there")
        await out.send_text_message("user1", "How are you?")
        assert out.get_accumulated_text() == "Hello there How are you?"

    @pytest.mark.asyncio
    async def test_send_text_message_single(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_text_message("user1", "Just one message")
        assert out.get_accumulated_text() == "Just one message"

    @pytest.mark.asyncio
    async def test_get_accumulated_text_empty(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        assert out.get_accumulated_text() == ""

    @pytest.mark.asyncio
    async def test_send_text_with_buttons_appends_options(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        buttons = [{"title": "Yes"}, {"title": "No"}, {"title": "Maybe"}]
        await out.send_text_with_buttons("user1", "Is this correct?", buttons)
        text = out.get_accumulated_text()
        assert "Is this correct?" in text
        assert "Yes" in text
        assert "No" in text
        assert "Maybe" in text
        assert "Options:" in text

    @pytest.mark.asyncio
    async def test_send_image_url_is_noop(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_image_url("user1", "https://example.com/image.png")
        assert out.get_accumulated_text() == ""
        assert len(out._messages) == 0

    @pytest.mark.asyncio
    async def test_send_attachment_is_noop(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_attachment("user1", "https://example.com/file.pdf")
        assert out.get_accumulated_text() == ""
        assert len(out._messages) == 0

    @pytest.mark.asyncio
    async def test_send_custom_json_with_text_field(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_custom_json("user1", {"text": "Custom message"})
        assert out.get_accumulated_text() == "Custom message"

    @pytest.mark.asyncio
    async def test_send_custom_json_with_data_text(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_custom_json("user1", {"data": {"text": "Nested text"}})
        assert out.get_accumulated_text() == "Nested text"

    @pytest.mark.asyncio
    async def test_send_custom_json_without_text_is_noop(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_custom_json("user1", {"type": "image", "url": "https://example.com/img.png"})
        assert out.get_accumulated_text() == ""

    def test_name_returns_voice(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        from kairon.shared.constants import ChannelTypes
        assert VoiceOutput.name() == ChannelTypes.VOICE.value


class TestVoiceHandler:

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))

    def _make_channel_config(self):
        return {
            "connector_type": "voice",
            "config": {
                "account_sid": Utility.encrypt_message("ACtest1234567890"),
                "auth_token": Utility.encrypt_message("test_auth_token"),
                "phone_number": "+12025551234",
                "telephony_provider": "twilio",
                "voice_type": "Polly.Amy",
                "process_url": "https://agent.kairon.io/api/bot/testbot/channel/voice/twilio/process/TOKEN",
                "call_url": "https://agent.kairon.io/api/bot/testbot/channel/voice/twilio/call/TOKEN",
                "status_url": "https://agent.kairon.io/api/bot/testbot/channel/voice/twilio/call/status/TOKEN",
            },
        }

    def _make_user(self):
        user = MagicMock()
        user.account = "test_account"
        return user

    def _make_request(self, form_data=None):
        request = MagicMock()
        request.form = AsyncMock(return_value=form_data or {})
        request.headers = {"X-Twilio-Signature": "test_signature"}
        return request

    def test_name_returns_voice(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.constants import ChannelTypes
        assert VoiceHandler.name() == ChannelTypes.VOICE.value

    @pytest.mark.asyncio
    async def test_validate_returns_ok(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        handler = VoiceHandler("testbot", self._make_user(), MagicMock(), "twilio")
        result = await handler.validate()
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_handle_message_raises_not_implemented(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        handler = VoiceHandler("testbot", self._make_user(), MagicMock(), "twilio")
        with pytest.raises(NotImplementedError):
            await handler.handle_message()

    @pytest.mark.asyncio
    async def test_handle_incoming_call_invalid_signature_returns_403(self):
        from fastapi import HTTPException
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"CallSid": "CA123", "From": "+1"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=False,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await handler.handle_incoming_call()
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_handle_incoming_call_valid_signature_returns_twiml(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"CallSid": "CA123", "From": "+1"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                result = await handler.handle_incoming_call()

        assert "<Gather" in result
        assert "<Say" in result

    @pytest.mark.asyncio
    async def test_handle_call_processing_invalid_signature_returns_403(self):
        from fastapi import HTTPException
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"SpeechResult": "hello", "CallSid": "CA123"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=False,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await handler.handle_call_processing()
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_handle_call_processing_empty_speech_skips_rasa(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"SpeechResult": "", "CallSid": "CA123"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                with patch("kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message") as mock_agent:
                    result = await handler.handle_call_processing()

        mock_agent.assert_not_called()
        assert "<Gather" in result

    @pytest.mark.asyncio
    async def test_handle_call_processing_with_speech_calls_rasa(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"SpeechResult": "book a meeting", "CallSid": "CA123"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                with patch(
                    "kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message",
                    new_callable=AsyncMock,
                ) as mock_agent:
                    result = await handler.handle_call_processing()

        mock_agent.assert_called_once()
        call_args = mock_agent.call_args[0]
        assert call_args[0] == "testbot"
        user_msg = call_args[1]
        assert user_msg.text == "book a meeting"
        assert user_msg.sender_id == "CA123"
        assert "<Gather" in result

    @pytest.mark.asyncio
    async def test_handle_call_processing_uses_call_sid_as_sender_id(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        call_sid = "CAuniqueid99"
        request = self._make_request({"SpeechResult": "hello", "CallSid": call_sid})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                with patch(
                    "kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message",
                    new_callable=AsyncMock,
                ) as mock_agent:
                    await handler.handle_call_processing()

        user_msg = mock_agent.call_args[0][1]
        assert user_msg.sender_id == call_sid

    @pytest.mark.asyncio
    async def test_handle_call_status_invalid_signature_returns_403(self):
        from fastapi import HTTPException
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"CallStatus": "completed", "CallSid": "CA123"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=False,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await handler.handle_call_status()
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_handle_call_status_valid_signature_logs_status(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"CallStatus": "completed", "CallSid": "CA123"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.ChannelLogs"
                ) as mock_logs:
                    mock_logs.return_value = MagicMock()
                    await handler.handle_call_status()
        mock_logs.assert_called_once()

    def test_unknown_provider_raises_on_load(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request()
        handler = VoiceHandler("testbot", self._make_user(), request, "unknownprovider")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with pytest.raises(AppException, match="not implemented"):
                handler._load_provider()


class TestVoiceChannelConfigSave:

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))

    def test_get_voice_channel_endpoints_returns_three_urls(self):
        from kairon.shared.data.utils import DataUtility

        channel_config = {
            "bot": "testbot",
            "user": "testuser",
            "connector_type": "voice",
            "config": {"telephony_provider": "twilio"},
        }

        with patch(
            "kairon.shared.auth.Authentication.generate_integration_token",
            return_value=("TOKEN123", MagicMock()),
        ):
            endpoints = DataUtility.get_voice_channel_endpoints(channel_config)

        assert "call_url" in endpoints
        assert "process_url" in endpoints
        assert "status_url" in endpoints

    def test_get_voice_channel_endpoints_url_structure(self):
        from kairon.shared.data.utils import DataUtility

        channel_config = {
            "bot": "mybot",
            "user": "admin",
            "connector_type": "voice",
            "config": {"telephony_provider": "twilio"},
        }

        with patch(
            "kairon.shared.auth.Authentication.generate_integration_token",
            return_value=("MYTOKEN", MagicMock()),
        ):
            endpoints = DataUtility.get_voice_channel_endpoints(channel_config)

        assert "/mybot/channel/voice/twilio/call/MYTOKEN" in endpoints["call_url"]
        assert "/mybot/channel/voice/twilio/process/MYTOKEN" in endpoints["process_url"]
        assert "/mybot/channel/voice/twilio/call/status/MYTOKEN" in endpoints["status_url"]

    def test_get_voice_channel_endpoints_access_limit_covers_all_paths(self):
        from kairon.shared.data.utils import DataUtility

        channel_config = {
            "bot": "mybot",
            "user": "admin",
            "connector_type": "voice",
            "config": {"telephony_provider": "twilio"},
        }

        with patch(
            "kairon.shared.auth.Authentication.generate_integration_token",
            return_value=("TOKEN", MagicMock()),
        ) as mock_gen:
            DataUtility.get_voice_channel_endpoints(channel_config)

        _, kwargs = mock_gen.call_args
        access_limit = kwargs.get("access_limit", mock_gen.call_args[0][3] if len(mock_gen.call_args[0]) > 3 else [])
        assert any("/mybot/channel/voice/twilio" in a for a in access_limit), \
            "access_limit must cover voice endpoints"


    def test_save_channel_config_voice_returns_call_and_status_urls(self):
        """save_channel_config for voice returns {call_url, status_url} — process_url stored internally only."""
        from kairon.shared.chat.processor import ChatDataProcessor

        config = {
            "connector_type": "voice",
            "config": {
                "account_sid": Utility.encrypt_message("ACtest"),
                "auth_token": Utility.encrypt_message("auth"),
                "phone_number": "+1234567890",
            },
        }

        mock_channel = MagicMock()
        mock_channel.connector_type = "voice"
        mock_channel.config = config["config"].copy()
        mock_channel.bot = "testbot"
        mock_channel.user = "testuser"

        fake_endpoints = {
            "call_url": "https://agent/api/bot/testbot/channel/voice/twilio/call/T",
            "process_url": "https://agent/api/bot/testbot/channel/voice/twilio/process/T",
            "status_url": "https://agent/api/bot/testbot/channel/voice/twilio/call/status/T",
        }

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.side_effect = DoesNotExist
        mock_channels_cls.return_value = mock_channel

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with patch(
                "kairon.shared.chat.processor.DataUtility.get_voice_channel_endpoints",
                return_value=fake_endpoints,
            ):
                with patch("kairon.shared.chat.processor.Utility.validate_channel"):
                    result = ChatDataProcessor.save_channel_config(config, "testbot", "testuser")

        assert set(result.keys()) == {"call_url", "status_url"}
        assert result["call_url"] == fake_endpoints["call_url"]
        assert result["status_url"] == fake_endpoints["status_url"]


class TestSaveChannelConfigVoiceBranch:
    """
    Tests for the voice branch added to ChatDataProcessor.save_channel_config.
    Covers the code path that calls get_voice_channel_endpoints instead of
    get_channel_endpoint for voice connector_type.
    """

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))

    def _voice_config(self):
        return {
            "connector_type": "voice",
            "config": {
                "account_sid": Utility.encrypt_message("ACtest"),
                "auth_token": Utility.encrypt_message("authtest"),
                "phone_number": "+15550001234",
                "voice_type": "Polly.Amy",
            },
        }

    def _fake_endpoints(self):
        return {
            "call_url": "https://agent/api/bot/bot1/channel/voice/twilio/call/TOK",
            "process_url": "https://agent/api/bot/bot1/channel/voice/twilio/process/TOK",
            "status_url": "https://agent/api/bot/bot1/channel/voice/twilio/call/status/TOK",
        }

    def test_save_voice_config_returns_dict_not_string(self):
        from kairon.shared.chat.processor import ChatDataProcessor

        mock_channel = MagicMock()
        mock_channel.connector_type = "voice"
        mock_channel.config = self._voice_config()["config"].copy()
        mock_channel.bot = "bot1"
        mock_channel.user = "user@test.com"

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.side_effect = DoesNotExist
        mock_channels_cls.return_value = mock_channel

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with patch(
                "kairon.shared.chat.processor.DataUtility.get_voice_channel_endpoints",
                return_value=self._fake_endpoints(),
            ):
                with patch("kairon.shared.chat.processor.Utility.validate_channel"):
                    result = ChatDataProcessor.save_channel_config(
                        self._voice_config(), "bot1", "user@test.com"
                    )

        assert isinstance(result, dict)
        assert set(result.keys()) == {"call_url", "status_url"}

    def test_save_voice_config_stores_urls_back_into_channel_config(self):
        from kairon.shared.chat.processor import ChatDataProcessor

        mock_channel = MagicMock()
        mock_channel.connector_type = "voice"
        # Keep config as MagicMock so .update can be asserted

        endpoints = self._fake_endpoints()

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.side_effect = DoesNotExist
        mock_channels_cls.return_value = mock_channel

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with patch(
                "kairon.shared.chat.processor.DataUtility.get_voice_channel_endpoints",
                return_value=endpoints,
            ):
                with patch("kairon.shared.chat.processor.Utility.validate_channel"):
                    ChatDataProcessor.save_channel_config(
                        self._voice_config(), "bot1", "user@test.com"
                    )

        mock_channel.config.update.assert_called_once_with(endpoints)
        assert mock_channel.save.call_count == 2

    def test_save_voice_config_calls_get_voice_endpoints_not_get_channel_endpoint(self):
        from kairon.shared.chat.processor import ChatDataProcessor
        from kairon.shared.data.utils import DataUtility

        mock_channel = MagicMock()
        mock_channel.connector_type = "voice"
        mock_channel.config = self._voice_config()["config"].copy()

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.side_effect = DoesNotExist
        mock_channels_cls.return_value = mock_channel

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with patch.object(
                DataUtility, "get_voice_channel_endpoints", return_value=self._fake_endpoints()
            ) as mock_voice_ep:
                with patch.object(DataUtility, "get_channel_endpoint") as mock_chan_ep:
                    with patch("kairon.shared.chat.processor.Utility.validate_channel"):
                        ChatDataProcessor.save_channel_config(
                            self._voice_config(), "bot1", "user@test.com"
                        )

        mock_voice_ep.assert_called_once()
        mock_chan_ep.assert_not_called()

    def test_save_non_voice_config_calls_get_channel_endpoint_not_voice(self):
        """Regression: non-voice channels must still use the old single-URL flow."""
        from kairon.shared.chat.processor import ChatDataProcessor
        from kairon.shared.data.utils import DataUtility

        slack_config = {
            "connector_type": "slack",
            "config": {
                "bot_user_oAuth_token": Utility.encrypt_message("xoxb-test"),
                "slack_signing_secret": Utility.encrypt_message("secret"),
                "client_id": "cid",
                "client_secret": "csec",
                "is_primary": True,
                "team": {"id": "T123"},
            },
        }

        mock_channel = MagicMock()
        mock_channel.connector_type = "slack"
        # Keep config as MagicMock; routing uses configuration dict not channel.config

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.side_effect = DoesNotExist
        mock_channels_cls.return_value = mock_channel

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with patch.object(
                DataUtility, "get_voice_channel_endpoints"
            ) as mock_voice_ep:
                with patch.object(
                    DataUtility, "get_channel_endpoint", return_value="https://single_url"
                ) as mock_chan_ep:
                    with patch("kairon.shared.chat.processor.Utility.validate_channel"):
                        result = ChatDataProcessor.save_channel_config(
                            slack_config, "bot1", "user@test.com"
                        )

        mock_voice_ep.assert_not_called()
        mock_chan_ep.assert_called_once()
        assert result == "https://single_url"

    def test_save_voice_config_missing_required_field_raises(self):
        from kairon.shared.chat.processor import ChatDataProcessor

        bad_config = {
            "connector_type": "voice",
            "config": {
                # missing account_sid, auth_token
                "phone_number": "+1234567890",
            },
        }

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.side_effect = DoesNotExist
        mock_channels_cls.return_value = MagicMock()

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with pytest.raises((AppException, Exception)):
                ChatDataProcessor.save_channel_config(bad_config, "bot1", "user@test.com")

    def test_save_voice_config_update_existing_merges_config(self):
        """When voice channel already exists, config merge path is taken."""
        from kairon.shared.chat.processor import ChatDataProcessor

        existing_channel = MagicMock()
        existing_channel.connector_type = "voice"
        existing_channel.config = self._voice_config()["config"].copy()

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.return_value = existing_channel
        mock_channels_cls.return_value = existing_channel

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with patch(
                "kairon.shared.chat.processor.ChatDataProcessor._ChatDataProcessor__validate_config_for_update",
                return_value=self._voice_config()["config"],
            ):
                with patch(
                    "kairon.shared.chat.processor.DataUtility.get_voice_channel_endpoints",
                    return_value=self._fake_endpoints(),
                ):
                    with patch("kairon.shared.chat.processor.Utility.validate_channel"):
                        result = ChatDataProcessor.save_channel_config(
                            self._voice_config(), "bot1", "user@test.com"
                        )

        assert "call_url" in result
        assert "status_url" in result
        assert "process_url" not in result


class TestVoiceServiceEndpoints:
    """
    Service-level tests for voice endpoints using TestClient.
    Uses app.dependency_overrides for auth (correct FastAPI pattern).
    Error assertions check response body (kairon returns 200 JSON for all errors).
    """

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
        from kairon.chat.server import app
        self.__class__.app = app
        self.__class__.client = TestClient(app)

    def _channel_config(self, bot="svcbot"):
        return {
            "connector_type": "voice",
            "config": {
                "account_sid": Utility.encrypt_message("ACtest"),
                "auth_token": Utility.encrypt_message("authtest"),
                "phone_number": "+15550001234",
                "telephony_provider": "twilio",
                "voice_type": "Polly.Amy",
                "call_url": f"https://agent/api/bot/{bot}/channel/voice/twilio/call/TOKEN",
                "process_url": f"https://agent/api/bot/{bot}/channel/voice/twilio/process/TOKEN",
                "status_url": f"https://agent/api/bot/{bot}/channel/voice/twilio/call/status/TOKEN",
            },
        }

    def _mock_user(self):
        user = MagicMock()
        user.account = "test_account"
        user.email = "test@test.com"
        user.bot = "svcbot"
        return user

    def _override_auth(self, user=None):
        from kairon.shared.auth import Authentication
        mock_user = user or self._mock_user()

        async def _auth():
            return mock_user

        self.__class__.app.dependency_overrides[Authentication.authenticate_token_in_path_param] = _auth
        return mock_user

    def _clear_overrides(self):
        self.__class__.app.dependency_overrides.clear()

    # ── /call endpoint ──────────────────────────────────────────────

    def test_call_endpoint_invalid_token_returns_error(self):
        response = self.__class__.client.post(
            "/api/bot/svcbot/channel/voice/twilio/call/INVALIDTOKEN",
            data={"CallSid": "CA1", "From": "+1"},
        )
        # kairon converts all errors to 200 JSON with success=False
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_call_endpoint_channel_not_configured_returns_error(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                side_effect=DoesNotExist("Channels matching query does not exist."),
            ):
                response = self.__class__.client.post(
                    "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
                    data={"CallSid": "CA1", "From": "+1"},
                )
        finally:
            self._clear_overrides()
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_call_endpoint_invalid_twilio_signature_returns_403(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=False,
                ):
                    response = self.__class__.client.post(
                        "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
                        data={"CallSid": "CA1", "From": "+1"},
                    )
        finally:
            self._clear_overrides()
        # 403 converted to 200 JSON by exception handler
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_call_endpoint_valid_returns_xml(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=True,
                ):
                    response = self.__class__.client.post(
                        "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
                        data={"CallSid": "CA1", "From": "+1"},
                    )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "xml" in response.headers.get("content-type", "").lower()
        assert "<Gather" in response.text
        assert "<Say" in response.text

    def test_call_endpoint_response_contains_process_url(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=True,
                ):
                    response = self.__class__.client.post(
                        "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
                        data={"CallSid": "CA1"},
                    )
        finally:
            self._clear_overrides()

        assert "process" in response.text

    # ── /process endpoint ───────────────────────────────────────────

    def test_process_endpoint_invalid_token_returns_error(self):
        response = self.__class__.client.post(
            "/api/bot/svcbot/channel/voice/twilio/process/BADTOKEN",
            data={"SpeechResult": "hi", "CallSid": "CA2"},
        )
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_process_endpoint_invalid_twilio_signature_returns_403(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=False,
                ):
                    response = self.__class__.client.post(
                        "/api/bot/svcbot/channel/voice/twilio/process/TOKEN",
                        data={"SpeechResult": "hello", "CallSid": "CA2"},
                    )
        finally:
            self._clear_overrides()
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_process_endpoint_empty_speech_skips_rasa_returns_xml(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=True,
                ):
                    with patch(
                        "kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message"
                    ) as mock_agent:
                        response = self.__class__.client.post(
                            "/api/bot/svcbot/channel/voice/twilio/process/TOKEN",
                            data={"SpeechResult": "", "CallSid": "CA2"},
                        )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "xml" in response.headers.get("content-type", "").lower()
        mock_agent.assert_not_called()

    def test_process_endpoint_valid_speech_calls_rasa_returns_xml(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=True,
                ):
                    with patch(
                        "kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message",
                        new_callable=AsyncMock,
                    ) as mock_agent:
                        response = self.__class__.client.post(
                            "/api/bot/svcbot/channel/voice/twilio/process/TOKEN",
                            data={"SpeechResult": "what are your hours", "CallSid": "CA3"},
                        )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "xml" in response.headers.get("content-type", "").lower()
        assert "<Gather" in response.text
        mock_agent.assert_called_once()
        user_msg = mock_agent.call_args[0][1]
        assert user_msg.text == "what are your hours"
        assert user_msg.sender_id == "CA3"

    def test_process_endpoint_rasa_response_appears_in_twiml(self):
        self._override_auth()
        try:
            async def _inject_response(bot, user_msg):
                await user_msg.output_channel.send_text_message(
                    user_msg.sender_id, "We are open Monday to Friday 9am to 5pm."
                )

            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=True,
                ):
                    with patch(
                        "kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message",
                        side_effect=_inject_response,
                    ):
                        response = self.__class__.client.post(
                            "/api/bot/svcbot/channel/voice/twilio/process/TOKEN",
                            data={"SpeechResult": "what are your hours", "CallSid": "CA4"},
                        )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "Monday to Friday" in response.text

    def test_process_endpoint_channel_not_configured_returns_error(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                side_effect=DoesNotExist("Channels matching query does not exist."),
            ):
                response = self.__class__.client.post(
                    "/api/bot/svcbot/channel/voice/twilio/process/TOKEN",
                    data={"SpeechResult": "hello", "CallSid": "CA5"},
                )
        finally:
            self._clear_overrides()
        assert response.status_code == 200
        assert response.json().get("success") is False

    # ── /status endpoint ────────────────────────────────────────────

    def test_status_endpoint_invalid_token_returns_error(self):
        response = self.__class__.client.post(
            "/api/bot/svcbot/channel/voice/twilio/call/status/BADTOKEN",
            data={"CallStatus": "completed", "CallSid": "CA10"},
        )
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_status_endpoint_invalid_twilio_signature_returns_403(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=False,
                ):
                    response = self.__class__.client.post(
                        "/api/bot/svcbot/channel/voice/twilio/call/status/TOKEN",
                        data={"CallStatus": "completed", "CallSid": "CA10"},
                    )
        finally:
            self._clear_overrides()
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_status_endpoint_valid_returns_empty_twiml(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=True,
                ):
                    with patch(
                        "kairon.chat.handlers.channels.clients.voice.twilio.ChannelLogs"
                    ) as mock_logs:
                        mock_logs.return_value = MagicMock()
                        response = self.__class__.client.post(
                            "/api/bot/svcbot/channel/voice/twilio/call/status/TOKEN",
                            data={"CallStatus": "completed", "CallSid": "CA10"},
                        )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "xml" in response.headers.get("content-type", "").lower()
        assert "<Response" in response.text

    def test_status_endpoint_valid_logs_call_status(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                return_value=self._channel_config(),
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                    return_value=True,
                ):
                    with patch(
                        "kairon.chat.handlers.channels.clients.voice.twilio.ChannelLogs"
                    ) as mock_logs:
                        mock_instance = MagicMock()
                        mock_logs.return_value = mock_instance
                        self.__class__.client.post(
                            "/api/bot/svcbot/channel/voice/twilio/call/status/TOKEN",
                            data={"CallStatus": "failed", "CallSid": "CA11", "CallDuration": "0"},
                        )
        finally:
            self._clear_overrides()

        mock_logs.assert_called_once()
        kwargs = mock_logs.call_args[1]
        assert kwargs["status"] == "failed"
        assert kwargs["message_id"] == "CA11"

    def test_status_endpoint_channel_not_configured_returns_error(self):
        self._override_auth()
        try:
            with patch(
                "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                side_effect=DoesNotExist("Channels matching query does not exist."),
            ):
                response = self.__class__.client.post(
                    "/api/bot/svcbot/channel/voice/twilio/call/status/TOKEN",
                    data={"CallStatus": "completed", "CallSid": "CA12"},
                )
        finally:
            self._clear_overrides()
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_status_endpoint_all_call_statuses_accepted(self):
        """Twilio sends multiple status values — all should be logged without error."""
        for call_status in ["queued", "ringing", "in-progress", "completed", "failed", "busy", "no-answer"]:
            self._override_auth()
            try:
                with patch(
                    "kairon.chat.handlers.channels.voice.ChatDataProcessor.get_channel_config",
                    return_value=self._channel_config(),
                ):
                    with patch(
                        "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                        return_value=True,
                    ):
                        with patch(
                            "kairon.chat.handlers.channels.clients.voice.twilio.ChannelLogs"
                        ) as mock_logs:
                            mock_logs.return_value = MagicMock()
                            response = self.__class__.client.post(
                                "/api/bot/svcbot/channel/voice/twilio/call/status/TOKEN",
                                data={"CallStatus": call_status, "CallSid": "CA99"},
                            )
            finally:
                self._clear_overrides()
            assert response.status_code == 200, f"Failed for status: {call_status}"
            assert "xml" in response.headers.get("content-type", "").lower(), f"Wrong content-type for status: {call_status}"
