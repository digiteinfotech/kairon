from unittest import mock
from unittest.mock import patch

import pytest

from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.clients.whatsapp.on_premise import WhatsappOnPremise


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


