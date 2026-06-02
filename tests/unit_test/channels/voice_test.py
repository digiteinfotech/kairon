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
        assert provider.speech_model == "default"
        assert provider.enhanced == "false"

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

    def test_build_voice_response_single_message(self):
        provider = self._make_provider()
        call_url = "https://example.com/api/bot/testbot/channel/voice/twilio/call/TOKEN"
        twiml = provider.build_voice_response(["Hello there"], call_url)
        assert "<Gather" in twiml
        assert "action=" in twiml
        assert call_url in twiml
        assert "Hello there" in twiml
        assert "<Say" in twiml

    def test_build_voice_response_action_on_empty_result(self):
        provider = self._make_provider()
        twiml = provider.build_voice_response(["Hi"], "https://example.com/call")
        assert "actionOnEmptyResult" in twiml

    def test_build_voice_response_empty_messages_still_has_gather(self):
        provider = self._make_provider()
        twiml = provider.build_voice_response([], "https://example.com/call")
        assert "<Gather" in twiml
        assert "<Say" not in twiml

    def test_build_voice_response_multiple_messages_adds_pause(self):
        provider = self._make_provider()
        twiml = provider.build_voice_response(
            ["First message", "Second message", "Third message"],
            "https://example.com/call",
        )
        assert "First message" in twiml
        assert "Second message" in twiml
        assert "Third message" in twiml
        assert "<Pause" in twiml
        assert "<Gather" in twiml

    def test_build_voice_response_uses_voice_type(self):
        provider = self._make_provider(extra={"voice_type": "Polly.Kajal"})
        twiml = provider.build_voice_response(["Namaste"], "https://example.com/call")
        assert "Polly.Kajal" in twiml

    def test_build_voice_response_last_message_inside_gather(self):
        provider = self._make_provider()
        twiml = provider.build_voice_response(
            ["Early message", "Last message"], "https://example.com/call"
        )
        gather_start = twiml.index("<Gather")
        gather_end = twiml.index("</Gather>")
        assert twiml.index("Last message") > gather_start
        assert twiml.index("Last message") < gather_end
        assert twiml.index("Early message") < gather_start

    def test_build_voice_response_single_message_inside_gather(self):
        provider = self._make_provider()
        twiml = provider.build_voice_response(["Only message"], "https://example.com/call")
        gather_start = twiml.index("<Gather")
        gather_end = twiml.index("</Gather>")
        assert twiml.index("Only message") > gather_start
        assert twiml.index("Only message") < gather_end

    def test_build_voice_response_uses_language_config(self):
        provider = self._make_provider(extra={"language": "en-IN"})
        twiml = provider.build_voice_response(["Hello"], "https://example.com/call")
        assert "en-IN" in twiml

    def test_build_voice_response_default_language_is_en_us(self):
        provider = self._make_provider()
        twiml = provider.build_voice_response(["Hello"], "https://example.com/call")
        assert "en-US" in twiml

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
    async def test_send_text_with_buttons_appends_text_and_titles(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        buttons = [{"title": "Yes"}, {"title": "No"}, {"title": "Maybe"}]
        await out.send_text_with_buttons("user1", "Is this correct?", buttons)
        text = out.get_accumulated_text()
        assert "Is this correct?" in text
        assert "Yes" in text
        assert "No" in text
        assert "Maybe" in text

    @pytest.mark.asyncio
    async def test_send_text_with_buttons_separate_messages(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        buttons = [{"title": "Yes"}, {"title": "No"}]
        await out.send_text_with_buttons("user1", "Choose one:", buttons)
        msgs = out.get_messages()
        assert msgs == ["Choose one:", "Yes", "No"]

    @pytest.mark.asyncio
    async def test_get_messages_returns_copy(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        await out.send_text_message("u", "Hello")
        msgs = out.get_messages()
        assert msgs == ["Hello"]
        msgs.append("tampered")
        assert out.get_messages() == ["Hello"]

    @pytest.mark.asyncio
    async def test_get_messages_empty(self):
        from kairon.chat.handlers.channels.voice import VoiceOutput
        out = VoiceOutput()
        assert out.get_messages() == []

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

        request = self._make_request({"CallSid": "CA123", "CallStatus": "ringing"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        async def _inject(bot, user_msg):
            await user_msg.output_channel.send_text_message(user_msg.sender_id, "Hello!")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                with patch(
                    "kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message",
                    side_effect=_inject,
                ):
                    result = await handler.handle_incoming_call()

        assert "<Gather" in result
        assert "<Say" in result

    @pytest.mark.asyncio
    async def test_handle_incoming_call_ringing_sends_welcome_to_rasa(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"CallSid": "CA123", "CallStatus": "ringing"})
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
                    await handler.handle_incoming_call()

        mock_agent.assert_called_once()
        user_msg = mock_agent.call_args[0][1]
        assert user_msg.text == "Hello! How can I help you?"
        assert user_msg.sender_id == "CA123"

    @pytest.mark.asyncio
    async def test_handle_incoming_call_ringing_uses_custom_welcome_message(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        config = self._make_channel_config()
        config["config"]["welcomeMessage"] = "Welcome to Kairon!"
        request = self._make_request({"CallSid": "CA123", "CallStatus": "ringing"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=config):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                with patch(
                    "kairon.chat.handlers.channels.voice.AgentProcessor.handle_channel_message",
                    new_callable=AsyncMock,
                ) as mock_agent:
                    await handler.handle_incoming_call()

        user_msg = mock_agent.call_args[0][1]
        assert user_msg.text == "Welcome to Kairon!"

    @pytest.mark.asyncio
    async def test_handle_incoming_call_speech_result_goes_to_rasa(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"CallSid": "CA123", "SpeechResult": "book a meeting"})
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
                    result = await handler.handle_incoming_call()

        mock_agent.assert_called_once()
        user_msg = mock_agent.call_args[0][1]
        assert user_msg.text == "book a meeting"
        assert user_msg.sender_id == "CA123"
        assert "<Gather" in result

    @pytest.mark.asyncio
    async def test_handle_incoming_call_speech_uses_call_sid_as_sender_id(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        call_sid = "CAunique9988"
        request = self._make_request({"CallSid": call_sid, "SpeechResult": "hello"})
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
                    await handler.handle_incoming_call()

        user_msg = mock_agent.call_args[0][1]
        assert user_msg.sender_id == call_sid

    @pytest.mark.asyncio
    async def test_handle_incoming_call_reprompt_on_empty_speech(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        from kairon.shared.chat.processor import ChatDataProcessor

        request = self._make_request({"CallSid": "CA123", "CallStatus": "in-progress"})
        handler = VoiceHandler("testbot", self._make_user(), request, "twilio")

        with patch.object(ChatDataProcessor, "get_channel_config", return_value=self._make_channel_config()):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.twilio.TwilioVoiceProvider.validate_signature",
                return_value=True,
            ):
                with patch(
                    "kairon.chat.handlers.channels.voice.AgentProcessor.get_agent",
                    side_effect=Exception("no agent"),
                ):
                    result = await handler.handle_incoming_call()

        assert "<Gather" in result
        assert "sorry" in result.lower() or "repeat" in result.lower()

    @pytest.mark.asyncio
    async def test_get_reprompt_returns_fallback_when_no_agent(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler

        handler = VoiceHandler("testbot", self._make_user(), MagicMock(), "twilio")
        with patch(
            "kairon.chat.handlers.channels.voice.AgentProcessor.get_agent",
            side_effect=Exception("no agent"),
        ):
            result = await handler._get_reprompt("CA1", {"reprompt_fallback_phrase": "Try again."})

        assert result == ["Try again."]

    @pytest.mark.asyncio
    async def test_get_reprompt_returns_default_fallback_when_no_config(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler

        handler = VoiceHandler("testbot", self._make_user(), MagicMock(), "twilio")
        with patch(
            "kairon.chat.handlers.channels.voice.AgentProcessor.get_agent",
            side_effect=Exception("no agent"),
        ):
            result = await handler._get_reprompt("CA1", {})

        assert len(result) == 1
        assert "sorry" in result[0].lower() or "repeat" in result[0].lower()

    @pytest.mark.asyncio
    async def test_get_reprompt_uses_last_bot_utterance(self):
        from rasa.shared.core.events import BotUttered
        from kairon.chat.handlers.channels.voice import VoiceHandler

        handler = VoiceHandler("testbot", self._make_user(), MagicMock(), "twilio")

        mock_event = MagicMock(spec=BotUttered)
        mock_event.text = "Your order is confirmed."
        mock_tracker = MagicMock()
        mock_tracker.events = [mock_event]
        mock_agent = MagicMock()
        mock_agent.tracker_store.retrieve = AsyncMock(return_value=mock_tracker)

        with patch(
            "kairon.chat.handlers.channels.voice.AgentProcessor.get_agent",
            return_value=mock_agent,
        ):
            result = await handler._get_reprompt("CA1", {})

        assert result == ["Your order is confirmed."]

    @pytest.mark.asyncio
    async def test_get_reprompt_falls_back_when_tracker_empty(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler

        handler = VoiceHandler("testbot", self._make_user(), MagicMock(), "twilio")
        mock_agent = MagicMock()
        mock_agent.tracker_store.retrieve = AsyncMock(return_value=None)

        with patch(
            "kairon.chat.handlers.channels.voice.AgentProcessor.get_agent",
            return_value=mock_agent,
        ):
            result = await handler._get_reprompt("CA1", {"reprompt_fallback_phrase": "Fallback."})

        assert result == ["Fallback."]

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

    def test_get_voice_channel_endpoints_returns_two_urls(self):
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
        assert "status_url" in endpoints
        assert "process_url" not in endpoints
        assert len(endpoints) == 2

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

    def test_save_voice_config_voice_disabled_raises(self):
        from kairon.shared.chat.processor import ChatDataProcessor
        from kairon.shared.data.processor import MongoProcessor

        mock_channel = MagicMock()
        mock_channel.connector_type = "voice"

        mock_channels_cls = MagicMock()
        mock_channels_cls.objects.return_value.get.side_effect = DoesNotExist
        mock_channels_cls.return_value = mock_channel

        with patch("kairon.shared.chat.processor.Channels", mock_channels_cls):
            with patch("kairon.shared.chat.processor.Utility.validate_channel"):
                with patch.object(MongoProcessor, "is_voice_enabled", return_value=False):
                    with pytest.raises(AppException, match="Voice is not enabled for this bot"):
                        ChatDataProcessor.save_channel_config(
                            self._voice_config(), "bot1", "user@test.com"
                        )


class TestVoiceServiceEndpoints:

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
        assert response.status_code == 200
        assert response.json().get("success") is False

    def test_call_endpoint_ringing_returns_xml(self):
        self._override_auth()

        async def _inject(bot, user_msg):
            await user_msg.output_channel.send_text_message(user_msg.sender_id, "Hello!")

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
                        side_effect=_inject,
                    ):
                        response = self.__class__.client.post(
                            "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
                            data={"CallSid": "CA1", "CallStatus": "ringing"},
                        )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "xml" in response.headers.get("content-type", "").lower()
        assert "<Gather" in response.text
        assert "<Say" in response.text

    def test_call_endpoint_speech_result_calls_rasa_returns_xml(self):
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
                            "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
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

    def test_call_endpoint_rasa_response_appears_in_twiml(self):
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
                            "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
                            data={"SpeechResult": "what are your hours", "CallSid": "CA4"},
                        )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "Monday to Friday" in response.text

    def test_call_endpoint_reprompt_on_empty_speech_returns_xml(self):
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
                        "kairon.chat.handlers.channels.voice.AgentProcessor.get_agent",
                        side_effect=Exception("no agent"),
                    ):
                        response = self.__class__.client.post(
                            "/api/bot/svcbot/channel/voice/twilio/call/TOKEN",
                            data={"CallSid": "CA5", "CallStatus": "in-progress"},
                        )
        finally:
            self._clear_overrides()

        assert response.status_code == 200
        assert "xml" in response.headers.get("content-type", "").lower()
        assert "<Gather" in response.text

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
