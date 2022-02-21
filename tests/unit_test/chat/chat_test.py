from kairon.shared.utils import Utility
import pytest
import os
from mongoengine import connect, ValidationError
from kairon.shared.chat.processor import ChatDataProcessor
from re import escape
import responses


class TestChat:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url

        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_save_channel_config_invalid(self):
        with pytest.raises(ValidationError, match="Invalid channel type custom"):
            ChatDataProcessor.save_channel_config({"connector_type": "custom",
                                                   "config": {
                                                       "slack_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                       "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                                  "test",
                                                  "test")

        with pytest.raises(ValidationError,
                           match=escape("Missing ['slack_token', 'slack_signing_secret'] all or any in config")):
            ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                                   "config": {
                                                       "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                                  "test",
                                                  "test")

        with pytest.raises(ValidationError,
                           match=escape("Missing ['slack_token', 'slack_signing_secret'] all or any in config")):
            ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                                   "config": {
                                                       "slack_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                   }},
                                                  "test",
                                                  "test")

    def test_save_channel_config(self):
        ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                               "config": {
                                                   "slack_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                   "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                              "test",
                                              "test")

    def test_update_channel_config(self):
        ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                               "config": {
                                                   "slack_token": "Test-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                   "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                              "test",
                                              "test")
        slack = ChatDataProcessor.get_channel_config("slack", "test", mask_characters=False)
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("slack_token")).startswith("Test")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_list_channel_config(self):
        channels = list(ChatDataProcessor.list_channel_config("test"))
        slack = channels[0]
        assert channels.__len__() == 1
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("slack_token")).__contains__("***")
        assert str(slack["config"].get("slack_signing_secret")).__contains__("***")

        channels = list(ChatDataProcessor.list_channel_config("test", mask_characters=False))
        slack = channels[0]
        assert channels.__len__() == 1
        assert slack.get("connector_type") == "slack"
        assert not str(slack["config"].get("slack_token")).__contains__("***")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_get_channel_config_slack(self):
        slack = ChatDataProcessor.get_channel_config("slack", "test")
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("slack_token")).__contains__("***")
        assert str(slack["config"].get("slack_signing_secret")).__contains__("***")

        slack = ChatDataProcessor.get_channel_config("slack", "test", mask_characters=False)
        assert slack.get("connector_type") == "slack"
        assert not str(slack["config"].get("slack_token")).__contains__("***")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_delete_channel_config_slack(self):
        ChatDataProcessor.delete_channel_config("slack", "test")
        assert list(ChatDataProcessor.list_channel_config("test")).__len__() == 0

    @responses.activate
    def test_save_channel_config_telegram(self):
        access_token = "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"
        webhook = "https://test@test.com/api/bot/telegram/tests/test"
        responses.add("GET",
                      json={'result': True},
                      url=f"{Utility.environment['channels']['telegram']['api']['url']}/bot{access_token}/setWebhook?url={webhook}")
        ChatDataProcessor.save_channel_config({"connector_type": "telegram",
                                               "config": {
                                                   "access_token": access_token,
                                                   "webhook_url": webhook,
                                                   "bot_name": "test"}},
                                              "test",
                                              "test")

    @responses.activate
    def test_save_channel_config_telegram_invalid(self):
        access_token = "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"
        webhook = "https://test@test.com/api/bot/telegram/tests/test"
        responses.add("GET",
                      json={'result': False, 'error_code': 400, 'description': "Invalid Webhook!"},
                      url=f"{Utility.environment['channels']['telegram']['api']['url']}/bot{access_token}/setWebhook?url={webhook}")
        with pytest.raises(ValidationError, match="Invalid Webhook!"):
            ChatDataProcessor.save_channel_config({"connector_type": "telegram",
                                                   "config": {
                                                       "access_token": access_token,
                                                       "webhook_url": webhook,
                                                       "bot_name": "test"}},
                                                  "test",
                                                  "test")
