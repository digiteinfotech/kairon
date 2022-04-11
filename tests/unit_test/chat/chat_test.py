from unittest.mock import patch
from urllib.parse import urlencode, quote_plus

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
                                                       "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                       "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                                  "test",
                                                  "test")

        with pytest.raises(ValidationError,
                           match=escape("Missing ['bot_user_oAuth_token', 'slack_signing_secret'] all or any in config")):
            ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                                   "config": {
                                                       "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                                  "test",
                                                  "test")

        with pytest.raises(ValidationError,
                           match=escape("Missing ['bot_user_oAuth_token', 'slack_signing_secret'] all or any in config")):
            ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                                   "config": {
                                                       "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                   }},
                                                  "test",
                                                  "test")

    def test_save_channel_config(self):
        ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                               "config": {
                                                   "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                   "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                              "test",
                                              "test")

    def test_update_channel_config(self):
        ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                               "config": {
                                                   "bot_user_oAuth_token": "Test-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                                   "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                              "test",
                                              "test")
        slack = ChatDataProcessor.get_channel_config("slack", "test", mask_characters=False)
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("bot_user_oAuth_token")).startswith("Test")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_list_channel_config(self):
        channels = list(ChatDataProcessor.list_channel_config("test"))
        slack = channels[0]
        assert channels.__len__() == 1
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("bot_user_oAuth_token")).__contains__("***")
        assert str(slack["config"].get("slack_signing_secret")).__contains__("***")

        channels = list(ChatDataProcessor.list_channel_config("test", mask_characters=False))
        slack = channels[0]
        assert channels.__len__() == 1
        assert slack.get("connector_type") == "slack"
        assert not str(slack["config"].get("bot_user_oAuth_token")).__contains__("***")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_get_channel_config_slack(self):
        slack = ChatDataProcessor.get_channel_config("slack", "test")
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("bot_user_oAuth_token")).__contains__("***")
        assert str(slack["config"].get("slack_signing_secret")).__contains__("***")

        slack = ChatDataProcessor.get_channel_config("slack", "test", mask_characters=False)
        assert slack.get("connector_type") == "slack"
        assert not str(slack["config"].get("bot_user_oAuth_token")).__contains__("***")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_delete_channel_config_slack(self):
        ChatDataProcessor.delete_channel_config("slack", "test")
        assert list(ChatDataProcessor.list_channel_config("test")).__len__() == 0

    @responses.activate
    def test_save_channel_config_telegram(self):
        access_token = "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"
        webhook = urlencode({'url': "https://test@test.com/api/bot/telegram/tests/test"}, quote_via=quote_plus)
        responses.add("GET",
                      json={'result': True},
                      url=f"{Utility.environment['channels']['telegram']['api']['url']}/bot{access_token}/setWebhook?{webhook}")

        def __mock_endpoint(*args):
            return f"https://test@test.com/api/bot/telegram/tests/test"

        with patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
            ChatDataProcessor.save_channel_config({"connector_type": "telegram",
                                               "config": {
                                                   "access_token": access_token,
                                                   "webhook_url": webhook,
                                                   "username_for_bot": "test"}},
                                              "test",
                                              "test")

    @responses.activate
    def test_save_channel_config_telegram_invalid(self):
        access_token = "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"
        webhook = {'url': "https://test@test.com/api/bot/telegram/tests/test"}
        webhook = urlencode(webhook, quote_via=quote_plus)
        responses.add("GET",
                      json={'result': False, 'error_code': 400, 'description': "Invalid Webhook!"},
                      url=f"{Utility.environment['channels']['telegram']['api']['url']}/bot{access_token}/setWebhook?{webhook}")
        with pytest.raises(ValidationError, match="Invalid Webhook!"):
            def __mock_endpoint(*args):
                return f"https://test@test.com/api/bot/telegram/tests/test"

            with patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
                ChatDataProcessor.save_channel_config({"connector_type": "telegram",
                                                       "config": {
                                                           "access_token": access_token,
                                                           "webhook_url": webhook,
                                                           "username_for_bot": "test"}},
                                                      "test",
                                                      "test")
