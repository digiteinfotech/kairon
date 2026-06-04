import os

from kairon.shared.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from unittest.mock import patch, MagicMock
import pytest

from kairon.exceptions import AppException
from kairon.shared.data.data_objects import (BotSettings
                                             )
from kairon.shared.data.processor import MongoProcessor
from mongoengine import connect


class TestVoiceEnabledFlag:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

    def test_is_voice_enabled_true(self):
        bot = 'voice_test_bot'
        user = 'voice_test_user'
        settings = BotSettings(bot=bot, user=user).save()
        settings.enable_voice = True
        settings.save()
        assert MongoProcessor.is_voice_enabled("voice_test_bot") is True

    def test_is_voice_enabled_false(self):
        bot = 'voice_test_bot'
        user = 'voice_test_user'
        settings = BotSettings.objects(bot=bot, user=user).get()
        settings.enable_voice = False
        settings.save()
        assert MongoProcessor.is_voice_enabled("voice_test_bot") is False

    def test_add_voice_call_action_voice_disabled_raises(self):
        processor = MongoProcessor()
        with patch.object(MongoProcessor, "is_voice_enabled", return_value=False):
            with pytest.raises(AppException, match="Voice is not enabled for this bot"):
                processor.add_voice_call_action(
                    {
                        "name": "test_action",
                        "to_phone_number": {"value": "+10000000000", "parameter_type": "value"},
                    },
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
                            {
                                "name": "test_action",
                                "to_phone_number": {"value": "+10000000000", "parameter_type": "value"},
                            },
                            "voice_test_bot", "voice_test_user",
                        )
            mock_doc.assert_called_once()

    def test_edit_voice_call_action_voice_disabled_raises(self):
        processor = MongoProcessor()
        with patch.object(MongoProcessor, "is_voice_enabled", return_value=False):
            with pytest.raises(AppException, match="Voice is not enabled for this bot"):
                processor.edit_voice_call_action(
                    {
                        "name": "test_action",
                        "to_phone_number": {"value": "+10000000000", "parameter_type": "value"},
                    },
                    "voice_test_bot", "voice_test_user",
                )
