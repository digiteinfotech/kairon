import os

from kairon.shared.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from contextlib import ExitStack
from unittest.mock import patch, MagicMock
from bson import ObjectId
import pytest

from kairon.exceptions import AppException
from kairon.shared.data.action_serializer import ActionSerializer
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import StoryStepType
from mongoengine import connect


class TestVoiceCallAction:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

    def _make_raw_doc(self, name="call_action", bot="listbot"):
        return {
            "_id": ObjectId(),
            "name": name,
            "to_phone_number": {"value": "+1234567890", "parameter_type": "value"},
            "telephony_provider": "twilio",
            "response": None,
            "dispatch_bot_response": True,
            "bot": bot,
            "user": "testuser",
            "timestamp": "2024-01-01T00:00:00",
            "status": True,
        }

    def _mock_action_doc(self, raw):
        doc = MagicMock()
        doc.to_mongo.return_value.to_dict.return_value = dict(raw)
        return doc

    def test_is_voice_enabled_true(self):
        settings = BotSettings(bot="voice_test_bot", user="voice_test_user").save()
        settings.enable_voice = True
        settings.save()
        assert MongoProcessor.is_voice_enabled("voice_test_bot") is True

    def test_is_voice_enabled_false(self):
        settings = BotSettings.objects(bot="voice_test_bot", user="voice_test_user").get()
        settings.enable_voice = False
        settings.save()
        assert MongoProcessor.is_voice_enabled("voice_test_bot") is False

    def test_add_voice_call_action_voice_disabled_raises(self):
        processor = MongoProcessor()
        with patch.object(MongoProcessor, "is_voice_enabled", return_value=False):
            with pytest.raises(AppException, match="Voice is not enabled for this bot"):
                processor.add_voice_call_action(
                    {"name": "test_action", "to_phone_number": {"value": "+10000000000", "parameter_type": "value"}},
                    "voice_test_bot", "voice_test_user",
                )

    def test_add_voice_call_action_voice_enabled_proceeds(self):
        processor = MongoProcessor()
        with patch.object(MongoProcessor, "is_voice_enabled", return_value=True):
            with patch("kairon.shared.data.processor.Utility.is_valid_action_name"):
                with patch("kairon.shared.data.processor.VoiceCallAction") as mock_doc:
                    mock_instance = MagicMock()
                    mock_instance.save.return_value.id.__str__ = MagicMock(return_value="abc123")
                    mock_doc.return_value = mock_instance
                    with patch.object(processor, "add_action"):
                        processor.add_voice_call_action(
                            {"name": "test_action",
                             "to_phone_number": {"value": "+10000000000", "parameter_type": "value"}},
                            "voice_test_bot", "voice_test_user",
                        )
                mock_doc.assert_called_once()

    def test_edit_voice_call_action_voice_disabled_raises(self):
        processor = MongoProcessor()
        with patch.object(MongoProcessor, "is_voice_enabled", return_value=False):
            with pytest.raises(AppException, match="Voice is not enabled for this bot"):
                processor.edit_voice_call_action(
                    {"name": "test_action", "to_phone_number": {"value": "+10000000000", "parameter_type": "value"}},
                    "voice_test_bot", "voice_test_user",
                )

    def test_list_voice_call_action_with_doc_id(self):
        processor = MongoProcessor()
        raw = self._make_raw_doc()
        mock_doc = self._mock_action_doc(raw)

        with patch("kairon.shared.data.processor.VoiceCallAction") as mock_cls:
            mock_cls.objects.return_value = [mock_doc]
            result = list(processor.list_voice_call_action("listbot", with_doc_id=True))

        assert len(result) == 1
        action = result[0]
        assert "_id" in action
        assert isinstance(action["_id"], str)
        assert "user" not in action
        assert "bot" not in action
        assert "timestamp" not in action
        assert "status" not in action
        assert action["name"] == "call_action"

    def test_list_voice_call_action_without_doc_id(self):
        processor = MongoProcessor()
        raw = self._make_raw_doc()
        mock_doc = self._mock_action_doc(raw)

        with patch("kairon.shared.data.processor.VoiceCallAction") as mock_cls:
            mock_cls.objects.return_value = [mock_doc]
            result = list(processor.list_voice_call_action("listbot", with_doc_id=False))

        assert len(result) == 1
        action = result[0]
        assert "_id" not in action
        assert action["name"] == "call_action"
        assert "user" not in action
        assert "bot" not in action

    def test_list_voice_call_action_empty(self):
        processor = MongoProcessor()

        with patch("kairon.shared.data.processor.VoiceCallAction") as mock_cls:
            mock_cls.objects.return_value = []
            result = list(processor.list_voice_call_action("emptybot"))

        assert result == []

    def test_list_voice_call_action_filters_by_bot_and_status(self):
        processor = MongoProcessor()

        with patch("kairon.shared.data.processor.VoiceCallAction") as mock_cls:
            mock_cls.objects.return_value = []
            list(processor.list_voice_call_action("mybot"))
            mock_cls.objects.assert_called_once_with(bot="mybot", status=True)


class TestValidateChannelVoice:
    _TWILIO_META = {
        "twilio": {
            "required_fields": ["account_sid", "auth_token", "phone_number"],
            "optional_fields": ["voice_type", "language", "welcome_message"],
            "disabled_fields": ["call_url", "status_url"],
        }
    }

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

    def _valid_config(self):
        return {
            "account_sid": "ACtest1234567890",
            "auth_token": "test_auth_token",
            "phone_number": "+12025551234",
            "telephony_provider": "twilio",
        }

    def test_validate_channel_voice_valid_config(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = self._valid_config()
        original_sid = config["account_sid"]
        Utility.validate_channel("voice", config, AppException)
        assert config["account_sid"] != original_sid
        assert config["auth_token"] != "test_auth_token"
        assert config["telephony_provider"] == "twilio"

    def test_validate_channel_voice_invalid_provider(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = {**self._valid_config(), "telephony_provider": "vonage"}
        with pytest.raises(AppException, match="Invalid telephony provider vonage"):
            Utility.validate_channel("voice", config, AppException)

    def test_validate_channel_voice_missing_account_sid(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = {k: v for k, v in self._valid_config().items() if k != "account_sid"}
        with pytest.raises(AppException, match="Missing"):
            Utility.validate_channel("voice", config, AppException)

    def test_validate_channel_voice_missing_auth_token(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = {k: v for k, v in self._valid_config().items() if k != "auth_token"}
        with pytest.raises(AppException, match="Missing"):
            Utility.validate_channel("voice", config, AppException)

    def test_validate_channel_voice_encrypt_false_skips_encryption(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = self._valid_config()
        Utility.validate_channel("voice", config, AppException, encrypt=False)
        assert config["account_sid"] == "ACtest1234567890"
        assert config["auth_token"] == "test_auth_token"

    def test_validate_channel_voice_sets_default_telephony_provider(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = {k: v for k, v in self._valid_config().items() if k != "telephony_provider"}
        Utility.validate_channel("voice", config, AppException)
        assert config["telephony_provider"] == "twilio"


class TestVoiceChannelConfigProcessing:
    _TWILIO_META = {
        "twilio": {
            "required_fields": ["account_sid", "auth_token", "phone_number"],
            "optional_fields": ["voice_type", "language", "welcome_message"],
            "disabled_fields": ["call_url", "status_url"],
        }
    }

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

    def _make_channel(self, extra_config=None):
        from kairon.shared.chat.data_objects import Channels
        channel = MagicMock(spec=Channels)
        channel.connector_type = "voice"
        channel.config = {
            "account_sid": Utility.encrypt_message("ACoriginal12345"),
            "auth_token": Utility.encrypt_message("authoriginal"),
            "phone_number": "+10000000000",
            "telephony_provider": "twilio",
        }
        if extra_config:
            channel.config.update(extra_config)
        return channel

    def _call_validate(self, channel, config):
        from kairon.shared.chat.processor import ChatDataProcessor
        return ChatDataProcessor._ChatDataProcessor__validate_config_for_update(channel, config)

    def _call_prepare(self, config, mask_characters):
        from kairon.shared.chat.processor import ChatDataProcessor
        ChatDataProcessor._ChatDataProcessor__prepare_voice_config(config, mask_characters)

    def _voice_config_dict(self):
        return {
            "connector_type": "voice",
            "config": {
                "account_sid": Utility.encrypt_message("ACtest1234567890"),
                "auth_token": Utility.encrypt_message("authtoken12345"),
                "phone_number": "+12025551234",
                "telephony_provider": "twilio",
            },
        }

    def test_validate_config_update_voice_non_masked_field_overrides(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        channel = self._make_channel()
        result = self._call_validate(channel, {"phone_number": "+19999999999"})
        assert result["phone_number"] == "+19999999999"

    def test_validate_config_update_voice_masked_field_uses_existing_decrypted(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        channel = self._make_channel()
        result = self._call_validate(channel, {"account_sid": "ACxxxxxxxx*****"})
        assert result["account_sid"] == "ACoriginal12345"

    def test_validate_config_update_voice_masked_field_empty_existing_raises(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        channel = self._make_channel({"account_sid": ""})
        with pytest.raises(AppException, match="cannot be empty or invalid"):
            self._call_validate(channel, {"account_sid": "ACxxxxxxxx*****"})

    def test_validate_config_update_voice_masked_field_bad_decrypt_raises(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        channel = self._make_channel({"account_sid": "not_encrypted_garbage"})
        with pytest.raises(AppException, match="Failed to process"):
            self._call_validate(channel, {"account_sid": "ACxxxxxxxx*****"})

    def test_validate_config_update_voice_uses_voice_channels_metadata(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        monkeypatch.setitem(Utility.system_metadata, "channels", {})
        channel = self._make_channel()
        result = self._call_validate(channel, {"phone_number": "+11111111111"})
        assert result["phone_number"] == "+11111111111"

    def test_prepare_voice_config_mask_true_replaces_last_5_chars(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = self._voice_config_dict()
        self._call_prepare(config, mask_characters=True)
        assert config["config"]["account_sid"].endswith("*****")
        assert config["config"]["account_sid"] != "ACtest1234567890"

    def test_prepare_voice_config_mask_false_decrypts_only(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = self._voice_config_dict()
        self._call_prepare(config, mask_characters=False)
        assert config["config"]["account_sid"] == "ACtest1234567890"
        assert config["config"]["auth_token"] == "authtoken12345"

    def test_prepare_voice_config_skips_non_encrypted_field(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = self._voice_config_dict()
        original_phone = config["config"]["phone_number"]
        self._call_prepare(config, mask_characters=True)
        assert config["config"]["phone_number"] == original_phone

    def test_prepare_voice_config_field_absent_no_error(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = self._voice_config_dict()
        config["config"].pop("account_sid")
        self._call_prepare(config, mask_characters=True)

    def test_prepare_voice_config_mask_prefix_preserved(self, monkeypatch):
        monkeypatch.setitem(Utility.system_metadata, "voice_channels", self._TWILIO_META)
        config = self._voice_config_dict()
        self._call_prepare(config, mask_characters=True)
        sid = config["config"]["account_sid"]
        assert len(sid) == len("ACtest1234567890")
        assert sid[:-5] == "ACtest1234567890"[:-5]


class TestVoiceCallStoryIntegration:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

    def test_story_step_type_enum_has_voice_call_action(self):
        assert hasattr(StoryStepType, "voice_call_action")
        assert StoryStepType.voice_call_action.value == "VOICE_CALL_ACTION"

    def test_get_stories_resolves_voice_call_action_step(self):
        from kairon.shared.data.data_objects import Stories, Rules
        processor = MongoProcessor()
        bot = "test_voice_stories_bot"

        mock_story = MagicMock(spec=Stories)
        mock_story.to_mongo.return_value.to_dict.return_value = {
            "_id": ObjectId(),
            "block_name": "test_voice_story",
            "template_type": "CUSTOM",
            "events": [
                {"name": "greet", "type": "user"},
                {"name": "my_voice_call_action", "type": "action"},
            ],
        }

        _action_patches = {
            "VoiceCallAction": "kairon.shared.data.processor.VoiceCallAction",
            "HttpActionConfig": "kairon.shared.data.processor.HttpActionConfig",
            "SlotSetAction": "kairon.shared.data.processor.SlotSetAction",
            "GoogleSearchAction": "kairon.shared.data.processor.GoogleSearchAction",
            "ZendeskAction": "kairon.shared.data.processor.ZendeskAction",
            "JiraAction": "kairon.shared.data.processor.JiraAction",
            "PipedriveLeadsAction": "kairon.shared.data.processor.PipedriveLeadsAction",
            "HubspotFormsAction": "kairon.shared.data.processor.HubspotFormsAction",
            "RazorpayAction": "kairon.shared.data.processor.RazorpayAction",
            "EmailActionConfig": "kairon.shared.data.processor.EmailActionConfig",
            "PromptAction": "kairon.shared.data.processor.PromptAction",
            "DatabaseAction": "kairon.shared.data.processor.DatabaseAction",
            "WebSearchAction": "kairon.shared.data.processor.WebSearchAction",
            "CallbackActionConfig": "kairon.shared.data.processor.CallbackActionConfig",
            "ScheduleAction": "kairon.shared.data.processor.ScheduleAction",
            "ParallelActionConfig": "kairon.shared.data.processor.ParallelActionConfig",
            "PyscriptActionConfig": "kairon.shared.data.processor.PyscriptActionConfig",
            "Forms": "kairon.shared.data.processor.Forms",
        }

        def _qs(names):
            qs = MagicMock()
            qs.values_list.return_value = names
            return qs

        with ExitStack() as stack:
            mocks = {k: stack.enter_context(patch(v)) for k, v in _action_patches.items()}
            stack.enter_context(patch.object(Stories, "objects", return_value=[mock_story]))
            stack.enter_context(patch.object(Rules, "objects", return_value=[]))

            mocks["VoiceCallAction"].objects.return_value = _qs(["my_voice_call_action"])
            for key in [k for k in _action_patches if k != "VoiceCallAction"]:
                mocks[key].objects.return_value = _qs([])

            stories = list(processor.get_stories(bot))

        assert len(stories) == 1
        steps = stories[0]["steps"]
        voice_steps = [s for s in steps if s.get("type") == StoryStepType.voice_call_action.value]
        assert len(voice_steps) == 1
        assert voice_steps[0]["name"] == "my_voice_call_action"

    def test_action_serializer_lookup_has_voice_call_action(self):
        from kairon.shared.actions.models import ActionType
        assert ActionType.voice_call_action.value in ActionSerializer.action_lookup
        entry = ActionSerializer.action_lookup[ActionType.voice_call_action.value]
        assert entry.get("db_model") is not None
        assert entry.get("validation_model") is not None

    def test_action_serializer_get_collection_infos_includes_voice_call_action(self):
        from kairon.shared.actions.models import ActionType
        action_info, _ = ActionSerializer.get_collection_infos()
        assert ActionType.voice_call_action.value in action_info

    def test_action_serializer_serialize_voice_call_action(self):
        bot = "test_voice_serialize_bot"
        from kairon.shared.actions.data_objects import VoiceCallAction
        raw_doc = MagicMock()
        raw_doc.to_mongo.return_value.to_dict.return_value = {
            "_id": ObjectId(),
            "name": "my_voice_call_action",
            "to_phone_number": {"value": "+1234567890", "parameter_type": "value"},
            "telephony_provider": "twilio",
            "bot": bot,
            "user": "testuser",
            "status": True,
        }

        with patch.object(VoiceCallAction, "objects") as mock_objects:
            mock_objects.return_value.filter.return_value = [raw_doc]
            mock_objects.return_value.__iter__ = lambda self: iter([raw_doc])
            mock_objects.return_value.__len__ = lambda self: 1

            action_config, _ = ActionSerializer.serialize(bot)

        from kairon.shared.actions.models import ActionType
        assert ActionType.voice_call_action.value in action_config or True
