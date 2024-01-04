import json
import os
from re import escape
from unittest.mock import patch
from urllib.parse import urlencode, quote_plus

import mongomock
import pytest
import responses
from mongoengine import connect, ValidationError
from pymongo.collection import Collection
from slack.web.slack_response import SlackResponse

from kairon.chat.handlers.channels.base import ChannelHandlerBase
from kairon.chat.utils import ChatUtils
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.chat.data_objects import Channels
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.data.constant import ACCESS_ROLES, TOKEN_TYPE
from kairon.shared.data.utils import DataUtility
from kairon.shared.utils import Utility
import mock
from pymongo.errors import ServerSelectionTimeoutError


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
            ChatDataProcessor.save_channel_config({
                "connector_type": "custom", "config": {
                    "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}}, "test", "test")

        with pytest.raises(AppException,
                           match=escape("Missing 'bot_user_oAuth_token' in config")):
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {"slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                "test", "test"
            )

        with patch("slack.web.client.WebClient.team_info") as mock_slack_resp:
            mock_slack_resp.return_value = SlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/team.info",
                req_args={},
                data={
                    "ok": True,
                    "team": {
                        "id": "T03BNQE7HLY",
                        "name": "helicopter",
                        "avatar_base_url": "https://ca.slack-edge.com/",
                        "is_verified": False
                    }
                },
                headers=dict(),
                status_code=200,
                use_sync_aiohttp=False,
            ).validate()
            with pytest.raises(ValidationError,
                               match=escape("Missing ['bot_user_oAuth_token', 'slack_signing_secret', 'client_id', 'client_secret'] all or any in config")):
                ChatDataProcessor.save_channel_config({
                    "connector_type": "slack", "config": {
                        "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"}}, "test",
                    "test"
                )

            with pytest.raises(ValidationError,
                               match=escape("Missing ['bot_user_oAuth_token', 'slack_signing_secret', 'client_id', 'client_secret'] all or any in config")):
                ChatDataProcessor.save_channel_config({
                    "connector_type": "slack", "config": {
                        "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
                        "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"}}, "test",
                    "test"
                )

            with pytest.raises(ValidationError,
                               match=escape("Missing ['bot_user_oAuth_token', 'slack_signing_secret', 'client_id', 'client_secret'] all or any in config")):
                ChatDataProcessor.save_channel_config({
                    "connector_type": "slack", "config": {
                        "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",  "client_id": "0987654321234567890",
                        "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"}}, "test",
                    "test"
                )

    @patch("kairon.shared.utils.Utility.get_slack_team_info", autospec=True)
    def test_save_channel_config_slack_team_id_error(self, mock_slack_info):
        mock_slack_info.side_effect = AppException("The request to the Slack API failed. ")
        with pytest.raises(AppException, match="The request to the Slack API failed.*"):
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}}, "test", "test"
            )

    def test_save_channel_config_slack(self, monkeypatch):
        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        with patch("slack.web.client.WebClient.team_info") as mock_slack_resp:
            mock_slack_resp.return_value = SlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/team.info",
                req_args={},
                data={
                    "ok": True,
                    "team": {
                        "id": "T03BNQE7HLY",
                        "name": "helicopter",
                        "avatar_base_url": "https://ca.slack-edge.com/",
                        "is_verified": False
                    }
                },
                headers=dict(),
                status_code=200,
                use_sync_aiohttp=False,
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": True}}, "test", "test"
            )

    @patch("kairon.shared.utils.Utility.get_slack_team_info", autospec=True)
    def test_save_channel_config_slack_secondary_app_team_id_error(self, mock_slack_info        ):
        mock_slack_info.side_effect = AppException("The request to the Slack API failed. ")
        with pytest.raises(AppException, match="The request to the Slack API failed.*"):
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": False}}, "test", "test"
            )

    def test_save_channel_config_slack_secondary_app(self, monkeypatch):
        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        with patch("slack.web.client.WebClient.team_info") as mock_slack_resp:
            mock_slack_resp.return_value = SlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/team.info",
                req_args={},
                data={
                    "ok": True,
                    "team": {
                        "id": "T03BNQE7HLX",
                        "name": "helicopter",
                        "avatar_base_url": "https://ca.slack-edge.com/",
                        "is_verified": False
                    }
                },
                headers=dict(),
                status_code=200,
                use_sync_aiohttp=False,
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-801478018484-801939352912-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": False}}, "test", "test"
            )

            mock_slack_resp.return_value = SlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/team.info",
                req_args={},
                data={
                    "ok": True,
                    "team": {
                        "id": "T03BNQE7HLZ",
                        "name": "airbus",
                        "avatar_base_url": "https://ca.slack-edge.com/",
                        "is_verified": False
                    }
                },
                headers=dict(),
                status_code=200,
                use_sync_aiohttp=False,
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-987654321098-801939352912-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": False}}, "test", "test"
            )

    def test_list_channels(self):
        channels = list(ChatDataProcessor.list_channel_config("test"))
        assert channels.__len__() == 3
        assert not Utility.check_empty_string(channels[0]['_id'])
        assert channels[0]['connector_type'] == 'slack'
        assert channels[0]['config'] == {
            'bot_user_oAuth_token': 'xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vamm*****',
            'slack_signing_secret': '79f036b9894eef17c064213b90d*****', 'client_id': '09876543212345*****',
            'client_secret': 'a23456789sfdghhtyutryu*****', 'is_primary': True,
            'team': {'id': 'T03BNQE7HLY', 'name': 'helicopter'}}
        assert not Utility.check_empty_string(channels[1]['_id'])
        assert channels[1]['connector_type'] == 'slack'
        assert channels[1]['config'] == {
            'bot_user_oAuth_token': 'xoxb-801478018484-801939352912-v3zq6MYNu62oSs8vamm*****',
            'slack_signing_secret': '79f036b9894eef17c064213b90d*****', 'client_id': '09876543212345*****',
            'client_secret': 'a23456789sfdghhtyutryu*****', 'is_primary': False,
            'team': {'id': 'T03BNQE7HLX', 'name': 'helicopter'}}
        assert not Utility.check_empty_string(channels[2]['_id'])
        assert channels[2]['connector_type'] == 'slack'
        assert channels[2]['config'] == {
            'bot_user_oAuth_token': 'xoxb-987654321098-801939352912-v3zq6MYNu62oSs8vamm*****',
            'slack_signing_secret': '79f036b9894eef17c064213b90d*****', 'client_id': '09876543212345*****',
            'client_secret': 'a23456789sfdghhtyutryu*****', 'is_primary': False,
            'team': {'id': 'T03BNQE7HLZ', 'name': 'airbus'}}

        channels = list(ChatDataProcessor.list_channel_config("test", mask_characters=False))
        assert channels.__len__() == 3
        assert not Utility.check_empty_string(channels[0]['_id'])
        assert channels[0]['connector_type'] == 'slack'
        assert channels[0]['config'] == {
            'bot_user_oAuth_token': 'xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K',
            'slack_signing_secret': '79f036b9894eef17c064213b90d1042b', 'client_id': '0987654321234567890',
            'client_secret': 'a23456789sfdghhtyutryuivcbn', 'is_primary': True,
            'team': {'id': 'T03BNQE7HLY', 'name': 'helicopter'}}
        assert not Utility.check_empty_string(channels[1]['_id'])
        assert channels[1]['connector_type'] == 'slack'
        assert channels[1]['config'] == {
            'bot_user_oAuth_token': 'xoxb-801478018484-801939352912-v3zq6MYNu62oSs8vammWOY8K',
            'slack_signing_secret': '79f036b9894eef17c064213b90d1042b', 'client_id': '0987654321234567890',
            'client_secret': 'a23456789sfdghhtyutryuivcbn', 'is_primary': False,
            'team': {'id': 'T03BNQE7HLX', 'name': 'helicopter'}}
        assert not Utility.check_empty_string(channels[2]['_id'])
        assert channels[2]['connector_type'] == 'slack'
        assert channels[2]['config'] == {
            'bot_user_oAuth_token': 'xoxb-987654321098-801939352912-v3zq6MYNu62oSs8vammWOY8K',
            'slack_signing_secret': '79f036b9894eef17c064213b90d1042b', 'client_id': '0987654321234567890',
            'client_secret': 'a23456789sfdghhtyutryuivcbn', 'is_primary': False,
            'team': {'id': 'T03BNQE7HLZ', 'name': 'airbus'}}

    def test_update_channel_config(self, monkeypatch):
        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        with patch("slack.web.client.WebClient.team_info") as mock_slack_resp:
            mock_slack_resp.return_value = SlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/team.info",
                req_args={},
                data={
                    "ok": True,
                    "team": {
                        "id": "T03BNQE7HLY",
                        "name": "helicopter",
                        "avatar_base_url": "https://ca.slack-edge.com/",
                        "is_verified": False
                    }
                },
                headers=dict(),
                status_code=200,
                use_sync_aiohttp=False,
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "Test-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042cd",
                    "client_id": "0987654321234567891", "client_secret": "a23456789sfdghhtyutryuivcbnu",
                    "is_primary": True
                }}, "test", "test")
        slack = ChatDataProcessor.get_channel_config("slack", "test", mask_characters=False, config__is_primary=True)
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("bot_user_oAuth_token")).startswith("Test")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_list_channel_config(self):
        channels = list(ChatDataProcessor.list_channel_config("test"))
        slack = channels[0]
        assert channels.__len__() == 1
        assert slack.get("connector_type") == "slack"
        assert slack["config"] == {'bot_user_oAuth_token': 'Test-801478018484-v3zq6MYNu62oSs8vamm*****',
                                   'slack_signing_secret': '79f036b9894eef17c064213b90d1*****',
                                   'client_id': '09876543212345*****', 'client_secret': 'a23456789sfdghhtyutryui*****',
                                   'is_primary': True, 'team': {'id': 'T03BNQE7HLY', 'name': 'helicopter'}}

        channels = list(ChatDataProcessor.list_channel_config("test", mask_characters=False))
        slack = channels[0]
        assert channels.__len__() == 1
        assert slack.get("connector_type") == "slack"
        assert slack["config"] == {'bot_user_oAuth_token': 'Test-801478018484-v3zq6MYNu62oSs8vammWOY8K',
                                   'slack_signing_secret': '79f036b9894eef17c064213b90d1042cd',
                                   'client_id': '0987654321234567891', 'client_secret': 'a23456789sfdghhtyutryuivcbnu',
                                   'is_primary': True, 'team': {'id': 'T03BNQE7HLY', 'name': 'helicopter'}}

    def test_get_channel_config_slack(self):
        slack = ChatDataProcessor.get_channel_config("slack", "test")
        assert slack.get("connector_type") == "slack"
        assert str(slack["config"].get("bot_user_oAuth_token")).__contains__("***")
        assert str(slack["config"].get("slack_signing_secret")).__contains__("***")

        slack = ChatDataProcessor.get_channel_config("slack", "test", mask_characters=False)
        assert slack.get("connector_type") == "slack"
        assert not str(slack["config"].get("bot_user_oAuth_token")).__contains__("***")
        assert not str(slack["config"].get("slack_signing_secret")).__contains__("***")

    def test_delete_channel_config_slack_secondary(self, monkeypatch):
        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        with patch("slack.web.client.WebClient.team_info") as mock_slack_resp:
            mock_slack_resp.return_value = SlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/team.info",
                req_args={},
                data={
                    "ok": True,
                    "team": {
                        "id": "T03BNQE7HLX",
                        "name": "helicopter",
                        "avatar_base_url": "https://ca.slack-edge.com/",
                        "is_verified": False
                    }
                },
                headers=dict(),
                status_code=200,
                use_sync_aiohttp=False,
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-801478018484-801939352912-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": False}}, "test", "test"
            )

            mock_slack_resp.return_value = SlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/team.info",
                req_args={},
                data={
                    "ok": True,
                    "team": {
                        "id": "T03BNQE7HLZ",
                        "name": "airbus",
                        "avatar_base_url": "https://ca.slack-edge.com/",
                        "is_verified": False
                    }
                },
                headers=dict(),
                status_code=200,
                use_sync_aiohttp=False,
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-987654321098-801939352912-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": False}}, "test", "test"
            )
            slack = ChatDataProcessor.get_channel_config("slack", "test", mask_characters=False, config__team__id="T03BNQE7HLX")
            ChatDataProcessor.delete_channel_config("test", id=slack['_id'])
            assert list(ChatDataProcessor.list_channel_config("test")).__len__() == 2

    def test_delete_channel_config_slack(self):
        ChatDataProcessor.delete_channel_config("test")
        assert list(ChatDataProcessor.list_channel_config("test")).__len__() == 0

    @responses.activate
    def test_save_channel_config_telegram(self):
        access_token = "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"
        webhook = urlencode({'url': "https://test@test.com/api/bot/telegram/tests/test"}, quote_via=quote_plus)
        responses.add("GET",
                      json={'result': True},
                      url=f"{Utility.system_metadata['channels']['telegram']['api']['url']}/bot{access_token}/setWebhook?{webhook}")

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
                      url=f"{Utility.system_metadata['channels']['telegram']['api']['url']}/bot{access_token}/setWebhook?{webhook}")
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

    @mock.patch('kairon.shared.utils.MongoClient', autospec=True)
    def test_fetch_session_history_error(self, mock_mongo):
        mock_mongo.side_effect = ServerSelectionTimeoutError("Failed to retrieve conversation: Failed to connect")
        history, message = ChatUtils.get_last_session_conversation("tests", "12345")
        assert len(history) == 0
        assert message.__contains__("Failed to retrieve conversation: Failed to connect")

    @mock.patch('kairon.shared.utils.MongoClient', autospec=True)
    def test_fetch_session_history_empty(self, mock_mongo):
        mock_mongo.return_value = mongomock.MongoClient()
        history, message = ChatUtils.get_last_session_conversation("tests", "12345")
        assert len(history) == 0
        assert message is None

    def test_fetch_session_history_exception(self, monkeypatch):
        def _mock_exception(*args, **kwargs):
            raise Exception('object out of memory')

        monkeypatch.setattr(Collection, 'aggregate', _mock_exception)
        monkeypatch.setitem(Utility.environment["database"], "url", "mongodb://localhost:3306")
        history, message = ChatUtils.get_last_session_conversation("tests", "12345")
        assert len(history) == 0
        assert message.__contains__("Failed to retrieve conversation: object out of memory")

    @mock.patch('kairon.shared.utils.MongoClient', autospec=True)
    def test_fetch_session_history(self, mock_mongo):
        import time
        bot = '5e564fbcdcf0d5fad89e3acd'
        test_db = Utility.environment['database']['test_db']
        mongo_client = mongomock.MongoClient("mongodb://test/conversations")
        db = mongo_client.get_database(test_db)
        collection = db.get_collection(bot)
        items = json.load(open("./tests/testing_data/history/conversations_history.json", "r"))
        for item in items:
            item['event']['timestamp'] = time.time()
            if not item["event"].get("metadata"):
                item["event"]["metadata"] = {}
            item["event"]["metadata"] = {"tabname": "coaching"}
        collection.insert_many(items)
        mock_mongo.return_value = mongo_client
        history, message = ChatUtils.get_last_session_conversation(bot, "fshaikh@digite.com")
        assert len(history) == 1
        assert history[0]["tabname"] == "coaching"
        assert len(history[0]["events"]) == 2
        assert message is None

    @responses.activate
    def test_save_channel_config_business_messages_with_invalid_private_key(self):
        def __mock_endpoint(*args):
            return f"https://test@test.com/api/bot/business_messages/tests/test"

        with patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
            channel_endpoint = ChatDataProcessor.save_channel_config(
                {
                    "connector_type": "business_messages",
                    "config": {
                        "type": "service_account",
                        "private_key_id": "fa006e13b1e17eddf3990eede45ca6111eb74945",
                        "private_key": "test_private_key\\n399045ca\\n6111eb74945",
                        "client_email": "provider@gbc-mahesh.iam.testaccount.com",
                        "client_id": "102056160806575769486"
                    }
                },
                "test",
                "test")
            assert channel_endpoint == "https://test@test.com/api/bot/business_messages/tests/test"
            business_messages_config = ChatDataProcessor.get_channel_config("business_messages",
                                                                            "test")
            assert business_messages_config['config'] == {'type': 'service_account',
                                                          'private_key_id': 'fa006e13b1e17eddf3990eede45ca6111eb*****',
                                                          'private_key': 'test_private_key\n399045ca\n6111eb*****',
                                                          'client_email': 'provider@gbc-mahesh.iam.testaccoun*****',
                                                          'client_id': '1020561608065757*****'}

    @responses.activate
    def test_save_channel_config_business_messages(self):
        def __mock_endpoint(*args):
            return f"https://test@test.com/api/bot/business_messages/tests/test"

        with patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
            channel_endpoint = ChatDataProcessor.save_channel_config(
                {
                    "connector_type": "business_messages",
                    "config": {
                        "type": "service_account",
                        "private_key_id": "fa006e13b1e17eddf3990eede45ca6111eb74945",
                        "private_key": "test_private_key",
                        "client_email": "provider@gbc-mahesh.iam.testaccount.com",
                        "client_id": "102056160806575769486"
                    }
                },
                "test",
                "test")
            assert channel_endpoint == "https://test@test.com/api/bot/business_messages/tests/test"
            business_messages_config = ChatDataProcessor.get_channel_config("business_messages",
                                                                            "test")
            assert business_messages_config['config'] == {'type': 'service_account',
                                                          'private_key_id': 'fa006e13b1e17eddf3990eede45ca6111eb*****',
                                                          'private_key': 'test_privat*****',
                                                          'client_email': 'provider@gbc-mahesh.iam.testaccoun*****',
                                                          'client_id': '1020561608065757*****'}

    def test_save_channel_config_msteams(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        monkeypatch.setattr(Authentication, "generate_integration_token", _get_integration_token)
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "msteams", "config": {
                "app_id": "app123",
                "app_secret": "appsecret123"
            }}, bot, "test@chat.com")
        msteams = ChatDataProcessor.get_channel_endpoint("msteams", bot)
        hashcode = channel_url.split("/", -1)[-1]
        dbhashcode = msteams.split("/", -1)[-1]
        assert hashcode == dbhashcode

    def test_get_channel_end_point_msteams(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        monkeypatch.setattr(Authentication, "generate_integration_token", _get_integration_token)
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "msteams", "config": {
                "app_id": "app123",
                "app_secret": "appsecret123"
            }}, bot, "test@chat.com")
        channel = Channels.objects(bot=bot, connector_type="msteams").get()
        response = DataUtility.get_channel_endpoint(channel)
        second_hashcode = response.split("/", -1)[-1]
        scnd_msteams = ChatDataProcessor.get_channel_config("msteams", bot, mask_characters=False)
        dbcode = scnd_msteams["meta_config"]["secrethash"]
        assert second_hashcode == dbcode

    def test_save_channel_meta_msteams(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        monkeypatch.setattr(Authentication, "generate_integration_token", _get_integration_token)

        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "msteams", "config": {
                "app_id": "app123",
                "app_secret": "appsecret123"
            }}, bot, "test@chat.com")
        token, _ = Authentication.generate_integration_token(
            bot, "test@chat.com", role=ACCESS_ROLES.CHAT.value,
            access_limit=[f"/api/bot/msteams/{bot}/.+"],
            token_type=TOKEN_TYPE.CHANNEL.value)
        channel = Channels.objects(bot=bot, connector_type="msteams").get()
        hashcode = DataUtility.save_channel_metadata(config=channel, token=token)
        channel_config = ChatDataProcessor.get_channel_config("msteams", bot, mask_characters=False)
        dbhashcode = channel_config["meta_config"]["secrethash"]
        assert hashcode == dbhashcode

    def test_get_channel_end_point_whatsapp(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _mock_generate_integration_token(*arge, **kwargs):
            return "testtoken", "ignore"

        with patch.object(Authentication, "generate_integration_token", _mock_generate_integration_token):
            channel_url = ChatDataProcessor.save_channel_config({
                "connector_type": "whatsapp", "config": {
                    "app_secret": "app123",
                    "access_token": "appsecret123", "verify_token": "integrate_1"
                }}, bot, "test@chat.com")
            channel = Channels.objects(bot=bot, connector_type="whatsapp").get()
            response = DataUtility.get_channel_endpoint(channel)
            last_urlpart = response.split("/", -1)[-1]
            assert last_urlpart == "testtoken"

    @pytest.mark.asyncio
    async def test_base_channel(self):
        with pytest.raises(NotImplementedError):
            await ChannelHandlerBase().validate()

        with pytest.raises(NotImplementedError):
            await ChannelHandlerBase().handle_message()
