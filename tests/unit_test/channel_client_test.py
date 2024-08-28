import os
from unittest import mock
from unittest.mock import patch

import pytest
import responses.matchers

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.clients.whatsapp.dialog360 import BSP360Dialog
from kairon.chat.handlers.channels.clients.whatsapp.on_premise import WhatsappOnPremise
from kairon.exceptions import AppException


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
                'https://graph.facebook.com/v19.0/messages',
                headers=whatsapp_on_premise.auth_args,
                json={'text': 'Hi'}, timeout=None
            )
            assert response == {"messages": [{"id": "test_id"}]}

    def test_send_action_failure(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'post') as mock_post:
            mock_post.return_value.json.return_value = {"error": {"message": "Message Undeliverable", "code": 400}}
            response = whatsapp_on_premise.send_action(payload={"text": " "})
            mock_post.assert_called_once_with(
                'https://graph.facebook.com/v19.0/messages',
                headers=whatsapp_on_premise.auth_args,
                json={'text': ' '}, timeout=None
            )
            assert response == {"error": {"message": "Message Undeliverable", "code": 400}}

    def test_get_attachment(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'get') as mock_get:
            mock_get.return_value.json.return_value = {"type": "document", "media_id": "test_media_id"}
            response = whatsapp_on_premise.get_attachment(media_id="test_media_id")
            mock_get.assert_called_once_with(
                'https://graph.facebook.com/v19.0/media/test_media_id',
                headers=whatsapp_on_premise.auth_args,
                timeout=None
            )
            assert response == {"type": "document", "media_id": "test_media_id"}

    def test_get_attachment_failure(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'get') as mock_get:
            mock_get.return_value.json.return_value = {"error": {"message": "media_id is not valid", "code": 400}}
            response = whatsapp_on_premise.get_attachment(media_id="invalid_id")
            mock_get.assert_called_once_with(
                'https://graph.facebook.com/v19.0/media/invalid_id',
                headers=whatsapp_on_premise.auth_args,
                timeout=None
            )
            assert response == {"error": {"message": "media_id is not valid", "code": 400}}

    def test_mark_as_read(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'put') as mock_put:
            mock_put.return_value.json.return_value = {"id": "test_msg_id"}
            response = whatsapp_on_premise.mark_as_read(msg_id="test_msg_id")
            mock_put.assert_called_once_with(
                'https://graph.facebook.com/v19.0/messages/test_msg_id',
                headers=whatsapp_on_premise.auth_args,
                json={'status': 'read'}, timeout=None
            )
            assert response == {"id": "test_msg_id"}

    def test_mark_as_read_failure(self, whatsapp_on_premise):
        with mock.patch.object(whatsapp_on_premise.session, 'put') as mock_put:
            mock_put.return_value.json.return_value = {"error": {"message": "msg_id is not valid", "code": 400}}
            response = whatsapp_on_premise.mark_as_read(msg_id="invalid_id")
            mock_put.assert_called_once_with(
                'https://graph.facebook.com/v19.0/messages/invalid_id',
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
            assert mock_send.call_args[0][1] == {'language': {'code': 'en', 'policy': 'deterministic'},
                                                 'name': 'test_template_name', 'namespace': 'test_namespace'}
            assert mock_send.call_args[0][2] == '9876543210'
            assert mock_send.call_args[1] == {'messaging_type': 'template'}

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
            assert mock_send.call_args[0][1] == {'language': {'code': 'en', 'policy': 'deterministic'},
                                                 'name': 'test_template_name', 'namespace': 'test_namespace'}
            assert mock_send.call_args[0][2] == 'invalid_ph_no'
            assert mock_send.call_args[1] == {'messaging_type': 'template'}

    def test_send_template_message_without_namespace(self, whatsapp_on_premise):
        name = "test_template_name"
        to_phone_number = "invalid_ph_no"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.on_premise.WhatsappOnPremise.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {"error": {"message": "to_phone_number is not valid", "code": 400}}

            with pytest.raises(AppException, match="namespace is required to send messages using on-premises api!"):
                whatsapp_on_premise.send_template_message(name=name, to_phone_number=to_phone_number)


class TestWhatsappCloud:

    @pytest.fixture(scope="module")
    def whatsapp_cloud(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        whatsapp_cloud = WhatsappCloud(access_token=access_token, from_phone_number_id=from_phone_number_id)
        yield whatsapp_cloud

    def test_whatsapp_cloud_send_template_message(self, whatsapp_cloud):
        name = "test_template_name"
        to_phone_number = "9876543210"
        components = {
            "type": "body",
            "parameters": [
                {
                    "type": "text",
                    "text": "text-string"
                },
                {
                    "type": "currency",
                    "currency": {
                        "fallback_value": "VALUE",
                        "code": "USD",
                        "amount_1000": "1000"
                    }
                },
                {
                    "type": "date_time",
                    "date_time": {
                        "fallback_value": "DATE"
                    }
                }
            ]
        }
        with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.WhatsappCloud.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
            response = whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                            components=components)
            assert mock_send.call_args[0][1] == {'language': {'code': 'en'}, 'name': 'test_template_name',
                                                 'components': {'type': 'body',
                                                                'parameters': [{'type': 'text', 'text': 'text-string'},
                                                                               {'type': 'currency',
                                                                                'currency': {'fallback_value': 'VALUE',
                                                                                             'code': 'USD',
                                                                                             'amount_1000': '1000'}},
                                                                               {'type': 'date_time', 'date_time': {
                                                                                   'fallback_value': 'DATE'}}]
                                                                }
                                                 }
            assert mock_send.call_args[0][2] == "9876543210"
            assert mock_send.call_args[1] == {'messaging_type': 'template'}
            assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

    def test_whatsapp_cloud_send_template_message_without_payload(self, whatsapp_cloud):
        name = "test_template_name"
        to_phone_number = "9876543210"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.WhatsappCloud.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
            response = whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number)
            assert mock_send.call_args[0][1] == {'language': {'code': 'en'}, 'name': 'test_template_name'}
            assert mock_send.call_args[0][2] == "9876543210"
            assert mock_send.call_args[1] == {'messaging_type': 'template'}
            assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

    def test_whatsapp_cloud_send_template_message_with_namespace(self, whatsapp_cloud):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "9876543210"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.WhatsappCloud.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
            response = whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                            namespace=namespace)
            assert mock_send.call_args[0][1] == {'language': {'code': 'en'}, 'name': 'test_template_name'}
            assert mock_send.call_args[0][2] == "9876543210"
            assert mock_send.call_args[1] == {'messaging_type': 'template'}
            assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

    def test_whatsapp_cloud_send_template_message_failure(self, whatsapp_cloud):
        name = "test_template_name"
        to_phone_number = "invalid_ph_no"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.WhatsappCloud.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {"error": {"message": "to_phone_number is not valid", "code": 400}}
            response = whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number)
            assert response == {"error": {"message": "to_phone_number is not valid", "code": 400}}

    @responses.activate
    def test_whatsapp_cloud_send_template_message_with_360dialog(self):
        name = "test_template_name"
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        to_phone_number = "9876543210"
        components = {
            "type": "body",
            "parameters": [
                {
                    "type": "text",
                    "text": "text-string"
                },
                {
                    "type": "currency",
                    "currency": {
                        "fallback_value": "VALUE",
                        "code": "USD",
                        "amount_1000": "1000"
                    }
                },
                {
                    "type": "date_time",
                    "date_time": {
                        "fallback_value": "DATE"
                    }
                }
            ]
        }

        responses.add(
            "POST", 'https://waba-v2.360dialog.io/messages',
            json={"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]},
            match=[responses.matchers.json_params_matcher({'messaging_product': 'whatsapp',
                                                           'recipient_type': 'individual', 'to': '9876543210',
                                                           'type': 'template',
                                                           'template': {'language': {'code': 'en'},
                                                                        'name': 'test_template_name',
                                                                        'components': {'type': 'body',
                                                                                       'parameters': [
                                                                                           {'type': 'text',
                                                                                            'text': 'text-string'},
                                                                                           {'type': 'currency',
                                                                                            'currency': {
                                                                                                'fallback_value': 'VALUE',
                                                                                                'code': 'USD',
                                                                                                'amount_1000': '1000'}},
                                                                                           {'type': 'date_time',
                                                                                            'date_time': {
                                                                                                'fallback_value': 'DATE'}}]}}}),
                   responses.matchers.header_matcher({'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'})]
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, from_phone_number_id=from_phone_number_id)
        response = whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                        components=components)
        assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

    @responses.activate
    def test_whatsapp_cloud_mark_read_360dialog(self):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"

        responses.add(
            "POST", 'https://waba-v2.360dialog.io/messages',
            json={"success": True},
            match=[responses.matchers.json_params_matcher({"messaging_product": "whatsapp", "status": "read",
                                                           "message_id": "ASDFHJKJT"}),
                   responses.matchers.header_matcher({'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'})]
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, from_phone_number_id=from_phone_number_id)
        response = whatsapp_cloud.mark_as_read("ASDFHJKJT")
        assert response == {"success": True}

    @responses.activate
    def test_whatsapp_cloud_send_template_message_with_360dialog_failure(self):
        name = "test_template_name"
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        to_phone_number = "9876543210"
        error_msg = {
            "error": {
                "message": "(#131009) Parameter value is not valid",
                "type": "OAuthException",
                "code": 131009,
                "error_data": {
                    "messaging_product": "whatsapp",
                    "details": "Please check the parameters you have provided."
                },
                "error_subcode": 2494010,
                "fbtrace_id": "A_lIoKUKB2unS85jgB4Gl7B"
            }
        }
        components = {
            "type": "body",
            "parameters": [
                {
                    "type": "text",
                    "text": "text-string"
                },
                {
                    "type": "currency",
                    "currency": {
                        "fallback_value": "VALUE",
                        "code": "USD",
                        "amount_1000": "1000"
                    }
                },
                {
                    "type": "date_time",
                    "date_time": {
                        "fallback_value": "DATE"
                    }
                }
            ]
        }

        responses.add(
            "POST", 'https://waba-v2.360dialog.io/messages',
            json=error_msg, status=404,
            match=[responses.matchers.json_params_matcher({'messaging_product': 'whatsapp',
                                                           'recipient_type': 'individual', 'to': '9876543210',
                                                           'type': 'template',
                                                           'template': {'language': {'code': 'en'},
                                                                        'name': 'test_template_name',
                                                                        'components': {'type': 'body',
                                                                                       'parameters': [
                                                                                           {'type': 'text',
                                                                                            'text': 'text-string'},
                                                                                           {'type': 'currency',
                                                                                            'currency': {
                                                                                                'fallback_value': 'VALUE',
                                                                                                'code': 'USD',
                                                                                                'amount_1000': '1000'}},
                                                                                           {'type': 'date_time',
                                                                                            'date_time': {
                                                                                                'fallback_value': 'DATE'}}]}}}),
                   responses.matchers.header_matcher({'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'})]
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, from_phone_number_id=from_phone_number_id)
        response = whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                        components=components)
        assert response == error_msg

    @responses.activate
    def test_whatsapp_cloud_mark_read_360dialog_failure(self):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        error_msg = {
            "error": {
                "message": "(#131009) Parameter value is not valid",
                "type": "OAuthException",
                "code": 131009,
                "error_data": {
                    "messaging_product": "whatsapp",
                    "details": "Please check the message ID you have provided."
                },
                "error_subcode": 2494010,
                "fbtrace_id": "A_lIoKUKB2unS85jgB4Gl7B"
            }
        }

        responses.add(
            "POST", 'https://waba-v2.360dialog.io/messages',
            json=error_msg, status=404,
            match=[responses.matchers.json_params_matcher({"messaging_product": "whatsapp", "status": "read",
                                                           "message_id": "ASDFHJKJT"}),
                   responses.matchers.header_matcher({'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'})]
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, from_phone_number_id=from_phone_number_id)
        response = whatsapp_cloud.mark_as_read("ASDFHJKJT")
        assert response == error_msg

    @responses.activate
    def test_whatsapp_cloud_send_message_with_360dialog(self):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        to_phone_number = "9876543210"
        payload = {
            "preview_url": True,
            "body": "You have to check out this amazing messaging service https://www.whatsapp.com/"
        }

        responses.add(
            "POST", 'https://waba-v2.360dialog.io/messages',
            json={"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]},
            match=[responses.matchers.json_params_matcher({
                'messaging_product': "whatsapp",
                'recipient_type': "individual",
                "to": to_phone_number,
                "type": "text",
                "text": payload
            }),
                responses.matchers.header_matcher({'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'})]
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, from_phone_number_id=from_phone_number_id)
        response = whatsapp_cloud.send(payload, to_phone_number, "text")
        assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

    @responses.activate
    def test_whatsapp_cloud_send_message_with_360dialog_failure(self):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        from_phone_number_id = "918958030415"
        to_phone_number = "9876543210"
        payload = {
            "preview_url": True,
            "body": "You have to check out this amazing messaging service https://www.whatsapp.com/"
        }
        error_msg = {
            "error": {
                "message": "(#131009) Parameter value is not valid",
                "type": "OAuthException",
                "code": 131009,
                "error_data": {
                    "messaging_product": "whatsapp",
                    "details": "Please check the message ID you have provided."
                },
                "error_subcode": 2494010,
                "fbtrace_id": "A_lIoKUKB2unS85jgB4Gl7B"
            }
        }

        responses.add(
            "POST", 'https://waba-v2.360dialog.io/messages', status=404,
            json=error_msg,
            match=[responses.matchers.json_params_matcher({
                'messaging_product': "whatsapp",
                'recipient_type': "individual",
                "to": to_phone_number,
                "type": "text",
                "text": payload
            }),
                responses.matchers.header_matcher({'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'})]
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, from_phone_number_id=from_phone_number_id)
        response = whatsapp_cloud.send(payload, to_phone_number, "text")
        assert response == error_msg
