import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from mongoengine import connect

from kairon.shared.utils import Utility

Utility.load_system_metadata()

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.actions.definitions.voice_call import ActionVoiceCall
from kairon.shared.actions.data_objects import VoiceCallAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.data.constant import STATUSES
from kairon.shared.actions.data_objects import CustomActionParameters


class TestActionVoiceCall:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.fixture
    def tracker(self):
        tracker = MagicMock()
        tracker.sender_id = "test_call_sid"
        tracker.get_slot.return_value = None
        tracker.get_intent_of_latest_message.return_value = "test_intent"
        tracker.latest_message = {"text": "call me"}
        return tracker

    @pytest.fixture
    def dispatcher(self):
        from rasa_sdk.executor import CollectingDispatcher
        return CollectingDispatcher()

    def _make_config(self, **kwargs):
        defaults = dict(
            name="test_voice_call_action",
            to_phone_number=CustomActionParameters(value="+10000000000", parameter_type="value"),
            telephony_provider="twilio",
            response="Calling you now.",
            dispatch_bot_response=True,
            bot="test_bot",
            user="test_user",
        )
        defaults.update(kwargs)
        return VoiceCallAction(**defaults).save()

    def _channel_config(self):
        return {
            "account_sid": "ACtest",
            "auth_token": "authtest",
            "phone_number": "+19999999999",
            "call_url": "https://example.com/call",
            "status_url": "https://example.com/status",
        }

    def test_retrieve_config_success(self):
        self._make_config(name="retrieve_ok", bot="bot_retrieve")
        config = ActionVoiceCall("bot_retrieve", "retrieve_ok").retrieve_config()
        assert config["name"] == "retrieve_ok"
        assert config["telephony_provider"] == "twilio"

    def test_retrieve_config_not_found(self):
        with pytest.raises(ActionFailure, match="No VoiceCallAction found"):
            ActionVoiceCall("nonexistent_bot", "nonexistent_action").retrieve_config()

    @pytest.mark.asyncio
    async def test_execute_literal_phone_success(self, tracker, dispatcher):
        self._make_config(name="exec_literal", bot="bot_exec")
        tracker.get_slot.return_value = "bot_exec"

        channel_cfg = self._channel_config()

        with patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                   return_value={"config": channel_cfg}), \
             patch("kairon.shared.voice.twilio.TwilioOutboundClient.initiate_call",
                   return_value="CA123") as mock_call, \
             patch("kairon.shared.chat.data_objects.ChannelLogs.save"), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionVoiceCall("bot_exec", "exec_literal").execute(
                dispatcher, tracker, {}, action_call={}
            )

        mock_call.assert_called_once_with("+10000000000", channel_cfg["call_url"], channel_cfg["status_url"])
        assert result["kairon_action_response"] == "Calling you now."
        assert any("Calling you now." in m["text"] for m in dispatcher.messages)

    @pytest.mark.asyncio
    async def test_execute_slot_phone_success(self, tracker, dispatcher):
        self._make_config(
            name="exec_slot",
            bot="bot_slot",
            to_phone_number=CustomActionParameters(value="phone_slot", parameter_type="slot"),
        )
        tracker.get_slot.side_effect = lambda k: "bot_slot" if k == "bot" else ("+15551234567" if k == "phone_slot" else None)

        with patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                   return_value={"config": self._channel_config()}), \
             patch("kairon.shared.voice.twilio.TwilioOutboundClient.initiate_call",
                   return_value="CA_slot") as mock_call, \
             patch("kairon.shared.chat.data_objects.ChannelLogs.save"), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionVoiceCall("bot_slot", "exec_slot").execute(
                dispatcher, tracker, {}, action_call={}
            )

        mock_call.assert_called_once_with("+15551234567", self._channel_config()["call_url"],
                                          self._channel_config()["status_url"])
        assert result["kairon_action_response"] == "Calling you now."

    @pytest.mark.asyncio
    async def test_execute_slot_phone_empty_raises(self, tracker, dispatcher):
        self._make_config(
            name="exec_slot_empty",
            bot="bot_slot_empty",
            to_phone_number=CustomActionParameters(value="missing_slot", parameter_type="slot"),
        )
        tracker.get_slot.return_value = None

        with patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                   return_value={"config": self._channel_config()}), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionVoiceCall("bot_slot_empty", "exec_slot_empty").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == "I have failed to place the call"

    @pytest.mark.asyncio
    async def test_execute_twilio_error_logs_failure(self, tracker, dispatcher):
        self._make_config(name="exec_twilio_err", bot="bot_twilio_err")
        tracker.get_slot.return_value = "bot_twilio_err"

        with patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                   return_value={"config": self._channel_config()}), \
             patch("kairon.shared.voice.twilio.TwilioOutboundClient.initiate_call",
                   side_effect=Exception("Twilio error")), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save") as mock_log:
            result = await ActionVoiceCall("bot_twilio_err", "exec_twilio_err").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == "I have failed to place the call"
        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_dispatch_bot_response_false(self, tracker, dispatcher):
        self._make_config(
            name="exec_no_dispatch",
            bot="bot_no_dispatch",
            dispatch_bot_response=False,
        )
        tracker.get_slot.return_value = "bot_no_dispatch"

        with patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                   return_value={"config": self._channel_config()}), \
             patch("kairon.shared.voice.twilio.TwilioOutboundClient.initiate_call",
                   return_value="CA_no_dispatch"), \
             patch("kairon.shared.chat.data_objects.ChannelLogs.save"), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionVoiceCall("bot_no_dispatch", "exec_no_dispatch").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == "Calling you now."
        assert len(dispatcher.messages) == 0

    @pytest.mark.asyncio
    async def test_execute_channel_config_not_found(self, tracker, dispatcher):
        self._make_config(name="exec_no_channel", bot="bot_no_channel")
        tracker.get_slot.return_value = "bot_no_channel"

        with patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                   side_effect=Exception("Channel not configured")), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionVoiceCall("bot_no_channel", "exec_no_channel").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == "I have failed to place the call"

    @pytest.mark.asyncio
    async def test_execute_unsupported_provider_raises(self, tracker, dispatcher):
        self._make_config(
            name="exec_bad_provider",
            bot="bot_bad_provider",
            telephony_provider="unsupported_provider",
        )
        tracker.get_slot.return_value = "bot_bad_provider"

        channel_cfg = self._channel_config()
        channel_cfg["telephony_provider"] = "unsupported_provider"

        with patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                   return_value={"config": channel_cfg}), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionVoiceCall("bot_bad_provider", "exec_bad_provider").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == "I have failed to place the call"

    def test_voice_outbound_factory_twilio(self):
        from kairon.shared.voice.factory import VoiceOutboundFactory
        from kairon.shared.voice.twilio import TwilioOutboundClient
        client_cls = VoiceOutboundFactory.get_client("twilio")
        assert client_cls is TwilioOutboundClient

    def test_voice_outbound_factory_unknown_raises(self):
        from kairon.shared.voice.factory import VoiceOutboundFactory
        with pytest.raises(ValueError, match="Unsupported voice provider"):
            VoiceOutboundFactory.get_client("unknown_provider")

    def test_twilio_outbound_client_calls_twilio_sdk(self):
        from kairon.shared.voice.twilio import TwilioOutboundClient
        client = TwilioOutboundClient("ACtest", "authtest", "+19999999999")

        mock_call = MagicMock()
        mock_call.sid = "CA_twilio_test"
        mock_twilio_client = MagicMock()
        mock_twilio_client.calls.create.return_value = mock_call

        with patch("twilio.rest.Client", return_value=mock_twilio_client):
            sid = client.initiate_call("+10000000001", "https://example.com/call",
                                       "https://example.com/status")

        assert sid == "CA_twilio_test"
        mock_twilio_client.calls.create.assert_called_once_with(
            to="+10000000001",
            from_="+19999999999",
            url="https://example.com/call",
            status_callback="https://example.com/status",
            status_callback_method="POST",
        )

    def test_action_type_enum_has_voice_call(self):
        assert hasattr(ActionType, "voice_call_action")
        assert ActionType.voice_call_action.value == "voice_call_action"

    def test_voice_call_action_config_validate_empty_action_name(self):
        with pytest.raises(Exception):
            VoiceCallAction(
                name="",
                to_phone_number=CustomActionParameters(value="+10000000000", parameter_type="value"),
                bot="bot",
                user="user",
            ).validate()
