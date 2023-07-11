import asyncio
import json
import os
from unittest import mock
from unittest.mock import patch

import responses
import pytest
from mongoengine import connect
from tornado.testing import AsyncHTTPTestCase

from kairon import Utility
from kairon.api.models import RegisterAccount
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.clients.whatsapp.on_premise import WhatsappOnPremise
from kairon.chat.handlers.channels.messenger import MessengerHandler
from kairon.chat.server import make_app
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.chat.processor import ChatDataProcessor

os.environ["system_file"] = "./tests/testing_data/system.yaml"
os.environ['ASYNC_TEST_TIMEOUT'] = "3600"
Utility.load_environment()
connect(**Utility.mongoengine_connection())

loop = asyncio.new_event_loop()
loop.run_until_complete(AccountProcessor.account_setup(RegisterAccount(**{"email": "test@chat.com",
                                                                          "first_name": "Test",
                                                                          "last_name": "Chat",
                                                                          "password": "testChat@12",
                                                                          "confirm_password": "testChat@12",
                                                                          "account": "ChatTesting"}).dict()))

token, _, _, _ = Authentication.authenticate("test@chat.com", "testChat@12")
user = AccountProcessor.get_complete_user_details("test@chat.com")
bot = user['bots']['account_owned'][0]['_id']
ChatDataProcessor.save_channel_config({
    "connector_type": "whatsapp",
    "config": {"app_secret": "jagbd34567890", "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ", "verify_token": "valid"}},
    bot, user="test@chat.com"
)


class TestWhatsapp(AsyncHTTPTestCase):

    def get_app(self):
        return make_app()

    @responses.activate
    @mock.patch("kairon.chat.handlers.channels.whatsapp.Whatsapp.process_message", autospec=True)
    def test_whatsapp_exception_when_try_to_handle_webhook_for_whatsapp_message(self, mock_process_message):
        def _mock_validate_hub_signature(*args, **kwargs):
            return True

        responses.add(
            "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
        )
        mock_process_message.side_effect = Exception
        with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
            response = self.fetch(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                method="POST",
                body=json.dumps({
                    "object": "whatsapp_business_account",
                    "entry": [{
                        "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                        "changes": [{
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "910123456789",
                                    "phone_number_id": "12345678"
                                },
                                "contacts": [{
                                    "profile": {
                                        "name": "udit"
                                    },
                                    "wa_id": "wa-123456789"
                                }],
                                "messages": [{
                                    "from": "910123456789",
                                    "id": "wappmsg.ID",
                                    "timestamp": "21-09-2022 12:05:00",
                                    "text": {
                                        "body": "hi"
                                    },
                                    "type": "text"
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 200)
        assert actual == 'success'


class TestWhatsappOnPremise:

    @pytest.fixture(scope="module")
    def whatsapp_on_premise(self):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        whatsapp_on_premise = WhatsappOnPremise(access_token=access_token, from_phone_number_id=from_phone_number_id)
        yield whatsapp_on_premise

    def test_send_action(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'post') as mock_post:
            mock_post.return_value.json.return_value = {"messages": [{"id": "test_id"}]}
            response = whatsapp_on_premise.send_action(payload={"text": "Hi"})
            mock_post.assert_called_once_with(
                'https://graph.facebook.com/v13.0/messages',
                headers=whatsapp_on_premise.auth_args,
                json={'text': 'Hi'}, timeout=None
            )
            assert response == {"messages": [{"id": "test_id"}]}

    def test_send_action_failure(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'post') as mock_post:
            mock_post.return_value.json.return_value = {"error": {"message": "Message Undeliverable", "code": 400}}
            response = whatsapp_on_premise.send_action(payload={"text": " "})
            mock_post.assert_called_once_with(
                'https://graph.facebook.com/v13.0/messages',
                headers=whatsapp_on_premise.auth_args,
                json={'text': ' '}, timeout=None
            )
            assert response == {"error": {"message": "Message Undeliverable", "code": 400}}

    def test_get_attachment(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'get') as mock_get:
            mock_get.return_value.json.return_value = {"type": "document", "media_id": "test_media_id"}
            response = whatsapp_on_premise.get_attachment(media_id="test_media_id")
            mock_get.assert_called_once_with(
                'https://graph.facebook.com/v13.0/media/test_media_id',
                headers=whatsapp_on_premise.auth_args,
                timeout=None
            )
            assert response == {"type": "document", "media_id": "test_media_id"}

    def test_get_attachment_failure(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'get') as mock_get:
            mock_get.return_value.json.return_value = {"error": {"message": "media_id is not valid", "code": 400}}
            response = whatsapp_on_premise.get_attachment(media_id="invalid_id")
            mock_get.assert_called_once_with(
                'https://graph.facebook.com/v13.0/media/invalid_id',
                headers=whatsapp_on_premise.auth_args,
                timeout=None
            )
            assert response == {"error": {"message": "media_id is not valid", "code": 400}}

    def test_mark_as_read(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'put') as mock_put:
            mock_put.return_value.json.return_value = {"id": "test_msg_id"}
            response = whatsapp_on_premise.mark_as_read(msg_id="test_msg_id")
            mock_put.assert_called_once_with(
                'https://graph.facebook.com/v13.0/messages/test_msg_id',
                headers=whatsapp_on_premise.auth_args,
                json={'status': 'read'}, timeout=None
            )
            assert response == {"id": "test_msg_id"}

    def test_mark_as_read_failure(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'put') as mock_put:
            mock_put.return_value.json.return_value = {"error": {"message": "msg_id is not valid", "code": 400}}
            response = whatsapp_on_premise.mark_as_read(msg_id="invalid_id")
            mock_put.assert_called_once_with(
                'https://graph.facebook.com/v13.0/messages/invalid_id',
                headers=whatsapp_on_premise.auth_args,
                json={'status': 'read'}, timeout=None
            )
            assert response == {"error": {"message": "msg_id is not valid", "code": 400}}

    def test_send_template_message(self, whatsapp_on_premise):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "9876543210"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.on_premise.WhatsappOnPremise.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
            response = whatsapp_on_premise.send_template_message(namespace=namespace, name=name,
                                                                 to_phone_number=to_phone_number)
            assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

    def test_send_template_message_failure(self, whatsapp_on_premise):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "invalid_ph_no"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.on_premise.WhatsappOnPremise.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {"error": {"message": "to_phone_number is not valid", "code": 400}}
            response = whatsapp_on_premise.send_template_message(namespace=namespace, name=name,
                                                                 to_phone_number=to_phone_number)
            assert response == {"error": {"message": "to_phone_number is not valid", "code": 400}}


class TestWhatsappCloud:

    @pytest.fixture(scope="module")
    def whatsapp_cloud(self):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        whatsapp_cloud = WhatsappCloud(access_token=access_token, from_phone_number_id=from_phone_number_id)
        yield whatsapp_cloud

    def test_whatsapp_cloud_send_template_message(self, whatsapp_cloud):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "9876543210"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.WhatsappCloud.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
            response = whatsapp_cloud.send_template_message(namespace=namespace, name=name,
                                                            to_phone_number=to_phone_number)
            assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

    def test_whatsapp_cloud_send_template_message_failure(self, whatsapp_cloud):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "invalid_ph_no"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.WhatsappCloud.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {"error": {"message": "to_phone_number is not valid", "code": 400}}
            response = whatsapp_cloud.send_template_message(namespace=namespace, name=name,
                                                            to_phone_number=to_phone_number)
            assert response == {"error": {"message": "to_phone_number is not valid", "code": 400}}


