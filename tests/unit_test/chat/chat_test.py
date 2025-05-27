import time
from unittest.mock import MagicMock, patch, AsyncMock

import ujson as json
import os
from re import escape
from unittest import mock
from urllib.parse import urlencode, quote_plus

import mongomock
import pytest
import responses
from mongoengine import connect, ValidationError
from slack_sdk.web.slack_response import SlackResponse

from kairon.chat.handlers.channels.base import ChannelHandlerBase
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.chat.data_objects import Channels
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.data.constant import ACCESS_ROLES, TOKEN_TYPE
from kairon.shared.data.utils import DataUtility
from kairon.shared.utils import Utility
from pymongo.errors import ServerSelectionTimeoutError
from rasa.shared.core.trackers import DialogueStateTracker


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

        with mock.patch("slack_sdk.web.client.WebClient.team_info") as mock_slack_resp:
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

    @mock.patch("kairon.shared.utils.Utility.get_slack_team_info", autospec=True)
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
        with mock.patch("slack_sdk.web.client.WebClient.team_info") as mock_slack_resp:
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
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": True}}, "test", "test"
            )

    @mock.patch("kairon.shared.utils.Utility.get_slack_team_info", autospec=True)
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
        with mock.patch("slack_sdk.web.client.WebClient.team_info") as mock_slack_resp:
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
            ).validate()
            ChatDataProcessor.save_channel_config({
                "connector_type": "slack", "config": {
                    "bot_user_oAuth_token": "xoxb-987654321098-801939352912-v3zq6MYNu62oSs8vammWOY8K",
                    "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "0987654321234567890",
                    "client_secret": "a23456789sfdghhtyutryuivcbn", "is_primary": False}}, "test", "test"
            )

    def test_save_whatsapp_failed_messages(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        json_message = {
            'data': [
                {
                    'type': 'button',
                    'value': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
                    'id': 1,
                    'children': [
                        {
                            'text': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
                        }
                    ]
                 }
            ],
            'type': 'button'
        }

        resp = {
            'error': {
                'message': '(#131009) Parameter value is not valid', 'type': 'OAuthException',
                'code': 131009,
                'error_data': {
                    'messaging_product': 'whatsapp',
                    'details': 'Button title length invalid. Min length: 1, Max length: 20'
                },
                'fbtrace_id': 'ALfhCiNWtld8enTUJyg0FFo'
            }
        }
        bot = "5e564fbcdcf0d5fad89e3abd"
        recipient = "919876543210"
        channel_type = "whatsapp"
        message_id = "wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggNjdDMUMxODhENEMyQUM1QzVBREQzN0YxQjQyNzA4MzAA"
        user = "91865712345"
        ChatDataProcessor.save_whatsapp_failed_messages(resp, bot, recipient, channel_type, json_message=json_message,
                                                        message_id=message_id, user=user)
        log = (
            ChannelLogs.objects(
                bot=bot,
                message_id="wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggNjdDMUMxODhENEMyQUM1QzVBREQzN0YxQjQyNzA4MzAA",
            )
            .get()
            .to_mongo()
            .to_dict()
        )
        print(log)
        assert log['type'] == 'whatsapp'
        assert log['data'] == resp
        assert log['status'] == 'failed'
        assert log['message_id'] == 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggNjdDMUMxODhENEMyQUM1QzVBREQzN0YxQjQyNzA4MzAA'
        assert log['failure_reason'] == 'Button title length invalid. Min length: 1, Max length: 20'
        assert log['recipient'] == '919876543210'
        assert log['type'] == 'whatsapp'
        assert log['user'] == '91865712345'
        assert log['json_message'] == {
            'data': [
                {
                    'type': 'button',
                    'value': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
                    'id': 1,
                    'children': [
                        {
                            'text': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
                        }
                    ]
                 }
            ],
            'type': 'button'
        }

    @pytest.mark.asyncio
    @mock.patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send", autospec=True)
    async def test_save_whatsapp_failed_messages_through_send_custom_json(self, mock_bsp):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.chat.handlers.channels.whatsapp import WhatsappBot
        from kairon.chat.handlers.channels.clients.whatsapp.dialog360 import BSP360Dialog

        json_message = {
            'data': [
                {
                    'type': 'button',
                    'value': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
                    'id': 1,
                    'children': [
                        {
                            'text': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
                        }
                    ]
                }
            ],
            'type': 'button'
        }

        resp = {
            'error': {
                'message': '(#131009) Parameter value is not valid', 'type': 'OAuthException',
                'code': 131009,
                'error_data': {
                    'messaging_product': 'whatsapp',
                    'details': 'Button title length invalid. Min length: 1, Max length: 20'
                },
                'fbtrace_id': 'ALfhCiNWtld8enTUJyg0FFo'
            }
        }
        mock_bsp.return_value = resp
        bot = "5e564fbcdcf0d5fad89e3abcd"
        recipient = "919876543210"
        user = "91865712345"
        channel_type = "whatsapp"
        metadata = {
            'from': '919876543210',
            'id': 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggNjdDMUMxODhENEMyQUM1QzVBREQzN0YxQjQyNzA4MzAA',
            'timestamp': '1732622052',
            'text': {'body': '/btn'},
            'type': 'text',
            'is_integration_user': True,
            'bot': bot,
            'account': 8,
            'channel_type': 'whatsapp',
            'bsp_type': '360dialog',
            'tabname': 'default',
            'display_phone_number': '91865712345',
            'phone_number_id': '142427035629239'
        }
        client = BSP360Dialog("asajjdkjskdkdjfk", metadata=metadata)
        await WhatsappBot(client).send_custom_json(recipient, json_message, assistant_id=bot)
        log = (
            ChannelLogs.objects(
                bot=bot,
                message_id="wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggNjdDMUMxODhENEMyQUM1QzVBREQzN0YxQjQyNzA4MzAA",
            )
            .get()
            .to_mongo()
            .to_dict()
        )
        assert log['type'] == 'whatsapp'
        assert log['data'] == resp
        assert log['status'] == 'failed'
        assert log['message_id'] == 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggNjdDMUMxODhENEMyQUM1QzVBREQzN0YxQjQyNzA4MzAA'
        assert log['failure_reason'] == 'Button title length invalid. Min length: 1, Max length: 20'
        assert log['recipient'] == '919876543210'
        assert log['type'] == 'whatsapp'
        assert log['user'] == '91865712345'
        assert log['json_message'] == {
            'data': [
                {
                    'type': 'button',
                    'value': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
                    'id': 1,
                    'children': [
                        {
                            'text': '/byeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
                        }
                    ]
                }
            ],
            'type': 'button'
        }
        assert log['metadata'] == {
            'from': recipient,
            'id': 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggNjdDMUMxODhENEMyQUM1QzVBREQzN0YxQjQyNzA4MzAA',
            'timestamp': '1732622052',
            'text': {'body': '/btn'},
            'type': 'text',
            'is_integration_user': True,
            'bot': bot,
            'account': 8,
            'channel_type': 'whatsapp',
            'bsp_type': '360dialog',
            'tabname': 'default',
            'display_phone_number': user,
            'phone_number_id': '142427035629239'
        }

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
        with mock.patch("slack_sdk.web.client.WebClient.team_info") as mock_slack_resp:
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
        with mock.patch("slack_sdk.web.client.WebClient.team_info") as mock_slack_resp:
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

        with mock.patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
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

            with mock.patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
                ChatDataProcessor.save_channel_config({"connector_type": "telegram",
                                                       "config": {
                                                           "access_token": access_token,
                                                           "webhook_url": webhook,
                                                           "username_for_bot": "test"}},
                                                      "test",
                                                      "test")

    @mock.patch('kairon.shared.utils.Utility.create_mongo_client', autospec=True)
    def test_fetch_session_history_error(self, mock_mongo):
        from kairon.chat.utils import ChatUtils

        mock_mongo.side_effect = ServerSelectionTimeoutError("Failed to retrieve conversation: Failed to connect")
        history, message = ChatUtils.get_last_session_conversation("tests", "12345")
        assert len(history) == 0
        assert message.__contains__("Failed to retrieve conversation: Failed to connect")

    @mock.patch('kairon.shared.utils.Utility.create_mongo_client', autospec=True)
    def test_fetch_session_history_empty(self, mock_mongo):
        from kairon.chat.utils import ChatUtils

        mock_mongo.return_value = mongomock.MongoClient()
        history, message = ChatUtils.get_last_session_conversation("tests", "12345")
        assert len(history) == 0
        assert message is None

    def test_fetch_session_history_exception(self, monkeypatch):
        from kairon.chat.utils import ChatUtils
        from mongomock.collection import Collection

        def _mock_exception(*args, **kwargs):
            raise Exception('object out of memory')

        def last_session(*args, **kwargs):
            return {'event': {'timestamp': time.time()}}

        monkeypatch.setattr(ChatUtils, 'get_last_session', last_session)
        monkeypatch.setattr(Collection, 'aggregate', _mock_exception)
        monkeypatch.setitem(Utility.environment["database"], "url", "mongodb://localhost:3306")
        history, message = ChatUtils.get_last_session_conversation("tests", "12345")
        print(history, message)
        assert len(history) == 0
        assert message.__contains__("Failed to retrieve conversation: object out of memory")

    @mock.patch('kairon.shared.utils.Utility.create_mongo_client', autospec=True)
    def test_fetch_session_history(self, mock_mongo):
        from kairon.chat.utils import ChatUtils
        import time
        bot = '5e564fbcdcf0d5fad89e3acd'
        test_db = Utility.environment['database']['test_db']
        mongo_client = mongomock.MongoClient("mongodb://test/conversations")
        db = mongo_client.get_database(test_db)
        collection = db.get_collection(bot)
        items = json.load(open("./tests/testing_data/history/conversations_history2.json", "r"))
        collection.insert_many(items)
        mock_mongo.return_value = mongo_client
        history, message = ChatUtils.get_last_session_conversation(bot, "spandan.mondal@nimblework.com")
        assert len(history) == 2
        assert history[1]["tabname"] == "default"
        assert len(history[0]["events"]) == 5
        assert len(history[1]["events"]) == 2
        history[1]["events"][0].pop("timestamp")
        history[1]["events"][0].pop("_id")

        assert history[1]["events"][0] == {
            'type': 'flattened', 'sender_id': 'spandan.mondal@nimblework.com',
            'conversation_id': '0190351c27607ebfa901061072d4906d',
            'data': {'user_input': 'hi', 'intent': 'greet', 'confidence': 0.9993663430213928,
                     'action': ['action_session_start',
                                'action_listen', 'utter_greet', 'action_listen'],
                     'bot_response': [{'text': 'Let me be your AI Assistant and provide you with service',
                                       'data': {'elements': None, 'quick_replies': None, 'buttons': None,
                                                'attachment': None, 'image': None, 'custom': None}}]},
            'metadata': {'tabname': 'default'}}
        assert message is None

    @responses.activate
    def test_save_channel_config_business_messages_with_invalid_private_key(self):
        def __mock_endpoint(*args):
            return f"https://test@test.com/api/bot/business_messages/tests/test"

        with mock.patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
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

        with mock.patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
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

        with mock.patch.object(Authentication, "generate_integration_token", _mock_generate_integration_token):
            channel_url = ChatDataProcessor.save_channel_config({
                "connector_type": "whatsapp", "config": {
                    "app_secret": "app123",
                    "access_token": "appsecret123", "verify_token": "integrate_1",
                    "phone_number": "01234567890"
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

    def test_save_channel_config_insta_with_no_comment_reply(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        monkeypatch.setattr(Authentication, "generate_integration_token", _get_integration_token)
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "instagram", "config": {
                "app_secret": "cdb69bc72e2ccb7a869f20cbb6b0229a",
                "page_access_token": "EAAGa50I7D7cBAJ4AmXOhYAeOOZAyJ9fxOclQmn52hBwrOJJWBOxuJNXqQ2uN667z4vLekSEqnCQf41hcxKVZAe2pAZBrZCTENEj1IBe1CHEcG7J33ZApED9Tj9hjO5tE13yckNa8lP3lw2IySFqeg6REJR3ZCJUvp2h03PQs4W5vNZBktWF3FjQYz5vMEXLPzAFIJcZApBtq9wZDZD",
                "verify_token": "kairon-instagram-token",
            }}, bot, "test@chat.com")
        insta_webhook = ChatDataProcessor.get_channel_endpoint("instagram", bot)
        hashcode = channel_url.split("/", -1)[-1]
        dbhashcode = insta_webhook.split("/", -1)[-1]
        assert hashcode == dbhashcode

        insta = ChatDataProcessor.get_channel_config("instagram", bot, False)

        static_comment_reply_actual = insta.get("config", {}).get("static_comment_reply")
        assert not static_comment_reply_actual

    def test_save_channel_config_insta_with_custom_comment_reply(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        monkeypatch.setattr(Authentication, "generate_integration_token", _get_integration_token)
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "instagram", "config": {
                "app_secret": "cdb69bc72e2ccb7a869f20cbb6b0229a",
                "page_access_token": "EAAGa50I7D7cBAJ4AmXOhYAeOOZAyJ9fxOclQmn52hBwrOJJWBOxuJNXqQ2uN667z4vLekSEqnCQf41hcxKVZAe2pAZBrZCTENEj1IBe1CHEcG7J33ZApED9Tj9hjO5tE13yckNa8lP3lw2IySFqeg6REJR3ZCJUvp2h03PQs4W5vNZBktWF3FjQYz5vMEXLPzAFIJcZApBtq9wZDZD",
                "verify_token": "kairon-instagram-token",
                "static_comment_reply": "Dhanyawad"
            }}, bot, "test@chat.com")
        insta_webhook = ChatDataProcessor.get_channel_endpoint("instagram", bot)
        hashcode = channel_url.split("/", -1)[-1]
        dbhashcode = insta_webhook.split("/", -1)[-1]
        assert hashcode == dbhashcode

        insta = ChatDataProcessor.get_channel_config("instagram", bot, False)

        static_comment_reply_actual = insta.get("config", {}).get("static_comment_reply")
        assert "Dhanyawad" == static_comment_reply_actual

    def test_save_channel_config_line(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        monkeypatch.setattr(Authentication, "generate_integration_token", _get_integration_token)
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "line", "config": {
            "channel_secret": "gAAAAABl8EZIcRrJMpxsgEiYK-M3sw2-k8deqiGPkuM1at4Y4hXN6wwD8SlxLaH1YGazfANEwZ9jd4nuILZQPIFIjOHDU6wCOpcOo4HxDpWWS5DJALXOl92Ez2DBIn8GTslg32PIDUv5",
            "channel_access_token": "gAAAAABl8EZISp9iqFhvOMgrfj1DZzDPPwLOD4_jJtgKDyTPKtEmNz1gYAIPVWU9Q_KjakEC81PdOuvOWju3gZm67jU-rvBxgMacW6kM7qgvFClZThlZEXl9Z01fxo-1BPnvAkCdDmbPUgaM1tvT77QlobDN_IDEXNlc3q-bo3PsvO0mYe29lwqvCkyFUnpdZRCqnHWtyL2qhARX18xS0SBr_c8jlQ8sUs_IcVozBlva4nUmZLWIo496jKtXObHRpVcrMJCqlu9oJ2tAtaT84KVO_q9VK_xHduU9Gu95EStehvamLMyC78k="
        }}, bot, "test@chat.com")
        line = ChatDataProcessor.get_channel_endpoint("line", bot)
        hashcode = channel_url.split("/", -1)[-1]
        dbhashcode = line.split("/", -1)[-1]
        assert hashcode == dbhashcode

    def test_get_channel_end_point_line(self, monkeypatch):
        bot = '5e564fbcdcf0d5fad89e3acd'

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        monkeypatch.setattr(Authentication, "generate_integration_token", _get_integration_token)
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "line", "config": {
                "channel_secret": "gAAAAABl8EZIcRrJMpxsgEiYK-M3sw2-k8deqiGPkuM1at4Y4hXN6wwD8SlxLaH1YGazfANEwZ9jd4nuILZQPIFIjOHDU6wCOpcOo4HxDpWWS5DJALXOl92Ez2DBIn8GTslg32PIDUv5",
                "channel_access_token": "gAAAAABl8EZISp9iqFhvOMgrfj1DZzDPPwLOD4_jJtgKDyTPKtEmNz1gYAIPVWU9Q_KjakEC81PdOuvOWju3gZm67jU-rvBxgMacW6kM7qgvFClZThlZEXl9Z01fxo-1BPnvAkCdDmbPUgaM1tvT77QlobDN_IDEXNlc3q-bo3PsvO0mYe29lwqvCkyFUnpdZRCqnHWtyL2qhARX18xS0SBr_c8jlQ8sUs_IcVozBlva4nUmZLWIo496jKtXObHRpVcrMJCqlu9oJ2tAtaT84KVO_q9VK_xHduU9Gu95EStehvamLMyC78k="
            }}, bot, "test@chat.com")
        channel = Channels.objects(bot=bot, connector_type="line").get()
        response = DataUtility.get_channel_endpoint(channel)
        second_hashcode = response.split("/", -1)[-1]
        line_2 = ChatDataProcessor.get_channel_config("line", bot, mask_characters=False)
        dbcode = line_2["meta_config"]["secrethash"]
        assert second_hashcode == dbcode

    @pytest.mark.asyncio
    async def test_mongotracker_save(self):
        from rasa.shared.core.events import SlotSet, SessionStarted, ActionExecuted, UserUttered, BotUttered, \
            DefinePrevUserUtteredFeaturization
        from rasa.shared.core.domain import Domain
        from kairon.shared.trackers import KMongoTrackerStore

        domain = Domain.load("./tests/testing_data/use-cases/Hi-Hello/domain.yml")
        sender_id = "test"
        bot="test_tracker"
        config = Utility.get_local_db()
        store = KMongoTrackerStore(domain=domain,
                                   host=config['host'],
                                   db=config['db'],
                                   collection=bot)

        tracker = DialogueStateTracker.from_events(sender_id=sender_id, evts=[], domain=domain)
        await store.save(tracker)

        data = list(store.client.get_database(config['db']).get_collection(bot).find({'type': 'bot'}))
        assert len(data) == 0
        data = list(store.client.get_database(config['db']).get_collection(bot).find({'type': 'flattened'}))
        assert len(data) == 0

        events = [
            SlotSet(key='session_started_metadata',
                    value={'tabname': 'default', 'is_integration_user': False, 'bot': '66a3595f6dbf82316083281b',
                           'account': 1, 'channel_type': 'chat_client'}),
            ActionExecuted(action_name='action_session_start', policy=None, confidence=1.0),
            SessionStarted(),
            SlotSet(key='session_started_metadata',
                    value={'tabname': 'default', 'is_integration_user': False, 'bot': '66a3595f6dbf82316083281b',
                           'account': 1, 'channel_type': 'chat_client'}),
            ActionExecuted(action_name='action_listen', policy=None, confidence=None),
            UserUttered(text='Hi', parse_data={'intent': {'name': "greet", 'confidence': 1.0}}),
            DefinePrevUserUtteredFeaturization(True),
            ActionExecuted(action_name='utter_please_rephrase', policy='RulePolicy', confidence=1.0),
            BotUttered('Sorry I didn\'t get that. Can you rephrase?',
                       {"elements": None, "quick_replies": None, "buttons": None, "attachment": None, "image": None,
                        "custom": None},
                       {"utter_action": "utter_please_rephrase", "model_id": "eda8e1b80fe04701a68c9a914f881eaf",
                        "assistant_id": "66a3595f6dbf82316083281b"}, 1721981387.4540014),
            ActionExecuted(action_name='action_listen', policy='RulePolicy', confidence=1.0)]
        tracker = DialogueStateTracker.from_events(sender_id=sender_id, evts=events, domain=domain)
        await store.save(tracker)

        data = list(store.client.get_database(config['db']).get_collection(bot).find({'type': 'bot'}))
        assert len(data) == len(events)
        assert data[0]['tag'] == 'tracker_store'
        assert data[0]['type'] == 'bot'
        data = list(store.client.get_database(config['db']).get_collection(bot).find({'type': 'flattened'}))
        assert len(data) == 1
        assert data[0]['tag'] == 'tracker_store'
        assert data[0]['type'] == 'flattened'


    def test_get_all_channel_configs(self):
        configs = list(ChatDataProcessor.get_all_channel_configs('telegram'))
        assert len(configs) == 1
        assert configs[0].get("connector_type") == "telegram"
        assert str(configs[0]["config"].get("access_token")).__contains__("***")

        configs = list(ChatDataProcessor.get_all_channel_configs('telegram', mask_characters=False))
        assert len(configs) == 1
        assert configs[0].get("connector_type") == "telegram"
        assert not str(configs[0]["config"].get("access_token")).__contains__("***")

    @patch('kairon.shared.channels.mail.scheduler.MailScheduler.request_epoch')
    @patch('kairon.shared.chat.processor.ChatDataProcessor.get_all_channel_configs')
    def test_mail_channel_save_duplicate_error(self, mock_get_all_channels, mock_request_epock, monkeypatch):
        def __get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __get_bot)

        mock_get_all_channels.return_value = [{
            'connector_type': 'mail',
            'bot': 'testbot3242',
            'config': {
                'email_account': 'test@example.com',
                'subjects': 'subject1,subject2'
            }
        }]

        #error case
        #same email and subject
        with pytest.raises(AppException, match='Email configuration already exists for same email address and subject'):
            ChatDataProcessor.save_channel_config({
                'connector_type': 'mail',
                'config': {
                    'email_account': 'test@example.com',
                    'subjects': 'subject1,subject2',
                    'email_password': 'test',
                    'imap_server': 'imap.gmail.com',
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': '587'
                }
            }, 'test', 'test')

        #same email partical subject overlap
        with pytest.raises(AppException, match='Email configuration already exists for same email address and subject'):
            ChatDataProcessor.save_channel_config({
                'connector_type': 'mail',
                'config': {
                    'email_account': 'test@example.com',
                    'subjects': 'subject1',
                    'email_password': 'test',
                    'imap_server': 'imap.gmail.com',
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': '587'
                }
            }, 'test', 'test')


        #non error case
        #different email and subject
        ChatDataProcessor.save_channel_config({
            'connector_type': 'mail',
            'config': {
                'email_account': 'test2@example.com',
                'subjects': '',
                'email_password': 'test',
                'imap_server': 'imap.gmail.com',
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': '587'
            }
        }, 'test', 'test')

        #different email same subject
        ChatDataProcessor.save_channel_config({
            'connector_type': 'mail',
            'config': {
                'email_account': 'test3@example.com',
                'subjects': '',
                'email_password': 'subject1,subject2',
                'imap_server': 'imap.gmail.com',
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': '587'
            }
        }, 'test', 'test')

        #same email different subject
        ChatDataProcessor.save_channel_config({
            'connector_type': 'mail',
            'config': {
                    'email_account': 'test@example.com',
                    'subjects': 'apple',
                    'email_password': 'test',
                    'imap_server': 'imap.gmail.com',
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': '587'
                }
        }, 'test', 'test')
        assert mock_request_epock.call_count == 3

        Channels.objects(connector_type='mail').delete()

@pytest.mark.asyncio
@patch("kairon.chat.utils.AgentProcessor.get_agent_without_cache")
@patch("kairon.chat.utils.ChatUtils.get_metadata")
async def test_process_messages_via_bot(mock_get_metadata, mock_get_agent_without_cache):
    messages = ["/greet", "/bye"]
    account = 1
    bot = "test_bot"
    users = ["test_user", "test_user2"]
    is_integration_user = False
    metadata = {"key": "value"}

    mock_get_metadata.return_value = metadata
    mock_model = MagicMock()
    mock_get_agent_without_cache.return_value = mock_model
    mock_model.handle_message = AsyncMock(side_effect=[{"text": "Hello"}, {"text": "Goodbye"}])
    from kairon.chat.utils import ChatUtils

    responses = await ChatUtils.process_messages_via_bot(messages, account, bot, users, is_integration_user, metadata)

    assert len(responses) == 2
    assert responses[0] == {"text": "Hello"}
    assert responses[1] == {"text": "Goodbye"}
    mock_get_metadata.assert_called_once_with(account, bot, is_integration_user, metadata)
    mock_get_agent_without_cache.assert_called_once_with(bot, False)
    assert mock_model.handle_message.call_count == 2



@pytest.mark.asyncio
async def test_handle_user_message_disallowed(monkeypatch):
    class DummyClient:
        pass

    Utility.environment['model'] = {
        'cache_size': 20
    }
    from kairon.chat.handlers.channels.messenger import Messenger, MessengerBot
    messenger = Messenger(page_access_token="dummy_token", is_instagram=True)
    messenger.allowed_users = ["allowed_user"]
    messenger.client = DummyClient()

    async def fake_get_username_for_id(self, sender_id):
        return "disallowed_user"

    monkeypatch.setattr(MessengerBot, "get_username_for_id", fake_get_username_for_id)

    process_called = False

    async def fake_process_message(bot, user_message):
        nonlocal process_called
        process_called = True

    monkeypatch.setattr(Messenger, "process_message", fake_process_message)

    await messenger._handle_user_message("test text", "sender1", {}, "testbot")

    assert not process_called
    del Utility.environment['model']




@pytest.mark.asyncio
async def test_get_username_for_id(monkeypatch):
    class DummyResponse:
        def __init__(self, json_data):
            self._json_data = json_data

        def json(self):
            return self._json_data

    class DummySession:
        def get(self, url):
            return DummyResponse({"username": "testuser"})

    class DummyClient:
        auth_args = {"access_token": "dummy_access_token"}
        graph_url = "http://dummy_graph_url"
        session = DummySession()
    Utility.environment['model'] = {
        'cache_size': 20
    }
    from kairon.chat.handlers.channels.messenger import MessengerBot
    messenger_bot = MessengerBot(DummyClient())

    async def fake_get_username_for_id(self, sender_id: str) -> str:
        params = f"fields=username&access_token={self.messenger_client.auth_args['access_token']}"
        url = f"{self.messenger_client.graph_url}/{sender_id}?{params}"
        assert "12345" in url
        resp = self.messenger_client.session.get(url)
        return resp.json().get('username')
    monkeypatch.setattr(MessengerBot, "get_username_for_id", fake_get_username_for_id)
    username = await messenger_bot.get_username_for_id("12345")

    assert username == "testuser"




@pytest.mark.asyncio
async def test_allowed_users_set_in_dev(monkeypatch):
    class DummyRequest:
        def __init__(self):
            self.headers = {"X-Hub-Signature": "dummy_signature"}
            self._body = b'{}'
            self.query_params = {"hub.verify_token": "dummy_verify_token", "hub.challenge": "123"}

        async def body(self):
            return self._body

        async def json(self):
            return {}

    class DummyUser:
        account = "dummy_account"

    class DummyActor:
        def execute(self, func, payload, metadata, bot):
            pass

    Utility.environment['model'] = {
        'cache_size': 20
    }
    from kairon.shared.concurrency.actors.factory import ActorFactory
    from kairon.chat.handlers.channels.messenger import InstagramHandler, Messenger

    dummy_config = {
        "config": {
            "is_dev": True,
            "allowed_users": "user1,user2",
            "app_secret": "dummy_secret",
            "page_access_token": "dummy_page_token",
            "verify_token": "dummy_verify_token",
        }
    }

    monkeypatch.setattr(
        ChatDataProcessor,
        "get_channel_config",
        lambda channel, bot, mask_characters: dummy_config
    )

    monkeypatch.setattr(
        InstagramHandler,
        "validate_hub_signature",
        lambda self, secret, payload, signature: True
    )

    monkeypatch.setattr(
        ActorFactory,
        "get_instance",
        lambda actor_type: DummyActor()
    )

    captured_messenger = None

    original_init = Messenger.__init__

    def fake_messenger_init(self, page_access_token, is_instagram=False):
        original_init(self, page_access_token, is_instagram)
        nonlocal captured_messenger
        captured_messenger = self

    monkeypatch.setattr(Messenger, "__init__", fake_messenger_init)

    dummy_request = DummyRequest()
    dummy_bot = "dummy_bot"
    dummy_user = DummyUser()

    handler = InstagramHandler(dummy_bot, dummy_user, dummy_request)

    result = await handler.handle_message()
    assert result == "success", "handle_message should return 'success'"

    assert captured_messenger is not None, "Messenger instance should be created"
    assert captured_messenger.allowed_users == ["user1", "user2"], (
        "allowed_users should be set to ['user1', 'user2']"
    )


@pytest.mark.asyncio
async def test_comment_with_static_comment_reply(monkeypatch):
    from kairon.chat.handlers.channels.messenger import Messenger, ChatDataProcessor
    message = {
        "field": "comments",
        "value": {
            "id": "comment123",
            "text": "This is a test comment",
            "from": {"username": "test_user"},
            "media": {
                "id": "media456",
                "media_product_type": "STORY"
            }
        }
    }
    metadata = {}
    bot = "test_bot"

    messenger = Messenger(page_access_token="dummy_token")

    monkeypatch.setattr(messenger, "_is_comment", lambda msg: True)
    monkeypatch.setattr(ChatDataProcessor, "get_instagram_static_comment", lambda bot: "Thanks for commenting!")
    monkeypatch.setattr(messenger, "get_user_id", lambda: "sender123")
    messenger._handle_user_message = AsyncMock()

    await messenger.comment(message, metadata, bot)

    assert metadata["comment_id"] == "comment123"
    assert metadata["static_comment_reply"] == "@test_user Thanks for commenting!"
    assert metadata["media_id"] == "media456"
    assert metadata["media_product_type"] == "STORY"

    messenger._handle_user_message.assert_awaited_once_with(
        "This is a test comment", "sender123", metadata, bot
    )

@pytest.mark.asyncio
async def test_comment_without_static_comment_reply(monkeypatch):
    from kairon.chat.handlers.channels.messenger import Messenger, ChatDataProcessor
    message = {
        "field": "comments",
        "value": {
            "id": "comment789",
            "text": "Another test comment",
            "from": {"username": "ghost_user"}
        }
    }
    metadata = {}
    bot = "test_bot"

    messenger = Messenger(page_access_token="dummy_token")

    monkeypatch.setattr(messenger, "_is_comment", lambda msg: True)
    monkeypatch.setattr(ChatDataProcessor, "get_instagram_static_comment", lambda bot: None)
    monkeypatch.setattr(messenger, "get_user_id", lambda: "sender789")

    messenger._handle_user_message = AsyncMock()

    await messenger.comment(message, metadata, bot)

    assert metadata["comment_id"] == "comment789"
    assert "static_comment_reply" not in metadata

    messenger._handle_user_message.assert_awaited_once_with(
        "Another test comment", "sender789", metadata, bot
    )

@pytest.mark.asyncio
@patch("kairon.chat.utils.UserMedia.upload_media_content_sync")
@patch("kairon.chat.utils.AgenticFlow.execute_rule")
@patch("kairon.chat.utils.AgenticFlow.__init__")
async def test_handle_media_agentic_flow_success(af_init, mock_execute_rule, mock_upload_media_content_sync):
    bot = "test_bot"
    sender_id = "user123"
    name = "test_flow"
    files = [MagicMock()]
    slot_vals = '{"key": "value"}'
    af_init.return_value = None

    mock_upload_media_content_sync.return_value = (["media_id_1"], None)

    mock_execute_rule.return_value = (["response_1"], None)

    from kairon.chat.utils import ChatUtils
    rsps, errors = await ChatUtils.handle_media_agentic_flow(bot, sender_id, name, files, slot_vals)

    assert rsps == ["response_1"]
    assert errors is None
    mock_upload_media_content_sync.assert_called_once_with(bot, sender_id, files)
    mock_execute_rule.assert_called_once()

@pytest.mark.asyncio
@patch("kairon.chat.utils.UserMedia.upload_media_content_sync")
async def test_handle_media_agentic_flow_invalid_slot_vals(mock_upload_media_content_sync):
    bot = "test_bot"
    sender_id = "user123"
    name = "test_flow"
    files = [MagicMock()]
    slot_vals = "invalid_json"

    mock_upload_media_content_sync.return_value = (["media_id_1"], None)

    from kairon.chat.utils import ChatUtils
    with pytest.raises(AppException, match="Invalid slot values format. Must be a valid JSON string."):
        await ChatUtils.handle_media_agentic_flow(bot, sender_id, name, files, slot_vals)

    mock_upload_media_content_sync.assert_called_once_with(bot, sender_id, files)