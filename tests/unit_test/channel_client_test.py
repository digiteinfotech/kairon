import os
from unittest.mock import patch

import pytest

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.clients.whatsapp.dialog360 import BSP360Dialog
from kairon.chat.handlers.channels.clients.whatsapp.on_premise import WhatsappOnPremise
from kairon.exceptions import AppException
from kairon.shared.rest_client import AioRestClient


class TestWhatsappOnPremise:

    @pytest.fixture(scope="module")
    def whatsapp_on_premise(self):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(False)
        from_phone_number_id = "918958030415"
        whatsapp_on_premise = WhatsappOnPremise(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        yield whatsapp_on_premise

    @pytest.mark.asyncio
    async def test_send_action(self, whatsapp_on_premise, aioresponses):
        aioresponses.post(
            'https://graph.facebook.com/v13.0/messages',
            payload={"messages": [{"id": "test_id"}]},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_on_premise.send_action(payload={"text": "Hi"})
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'text': 'Hi'}
        assert response == '{"messages": [{"id": "test_id"}]}'

    @pytest.mark.asyncio
    async def test_send_action_failure(self, whatsapp_on_premise, aioresponses):
        aioresponses.post(
            'https://graph.facebook.com/v13.0/messages',
            payload={"error": {"message": "Message Undeliverable", "code": 400}},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_on_premise.send_action(payload={"text": " "})
        assert response == '{"error": {"message": "Message Undeliverable", "code": 400}}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'text': ' '}

    @pytest.mark.asyncio
    async def test_get_attachment(self, whatsapp_on_premise, aioresponses):
        aioresponses.get(
            'https://graph.facebook.com/v13.0/media/test_media_id',
            payload={"type": "document", "media_id": "test_media_id"},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_on_premise.get_attachment(media_id="test_media_id")
        assert response == '{"type": "document", "media_id": "test_media_id"}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}

    @pytest.mark.asyncio
    async def test_get_attachment_failure(self, whatsapp_on_premise, aioresponses):
        aioresponses.get(
            'https://graph.facebook.com/v13.0/media/invalid_id',
            payload={"error": {"message": "media_id is not valid", "code": 400}},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_on_premise.get_attachment(media_id="invalid_id")
        assert response == '{"error": {"message": "media_id is not valid", "code": 400}}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}

    @pytest.mark.asyncio
    async def test_mark_as_read(self, whatsapp_on_premise, aioresponses):
        aioresponses.put(
            'https://graph.facebook.com/v13.0/messages/test_msg_id',
            payload={"id": "test_msg_id"},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_on_premise.mark_as_read(msg_id="test_msg_id")
        assert response == '{"id": "test_msg_id"}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}

    @pytest.mark.asyncio
    async def test_mark_as_read_failure(self, whatsapp_on_premise, aioresponses):
        aioresponses.put(
            'https://graph.facebook.com/v13.0/messages/invalid_id',
            payload={"error": {"message": "msg_id is not valid", "code": 400}},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_on_premise.mark_as_read(msg_id="invalid_id")
        assert response == '{"error": {"message": "msg_id is not valid", "code": 400}}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'status': 'read'}

    @pytest.mark.asyncio
    async def test_send_template_message(self, whatsapp_on_premise):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "9876543210"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.on_premise.WhatsappOnPremise.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
            response = await whatsapp_on_premise.send_template_message(namespace=namespace, name=name,
                                                                 to_phone_number=to_phone_number)
            assert response == {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
            assert mock_send.call_args[0][1] == {'language': {'code': 'en', 'policy': 'deterministic'},
                                                 'name': 'test_template_name', 'namespace': 'test_namespace'}
            assert mock_send.call_args[0][2] == '9876543210'
            assert mock_send.call_args[1] == {'messaging_type': 'template'}

    @pytest.mark.asyncio
    async def test_send_template_message_failure(self, whatsapp_on_premise):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "invalid_ph_no"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.on_premise.WhatsappOnPremise.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {"error": {"message": "to_phone_number is not valid", "code": 400}}
            response = await whatsapp_on_premise.send_template_message(namespace=namespace, name=name,
                                                                 to_phone_number=to_phone_number)
            assert response == {"error": {"message": "to_phone_number is not valid", "code": 400}}
            assert mock_send.call_args[0][1] == {'language': {'code': 'en', 'policy': 'deterministic'},
                                                 'name': 'test_template_name', 'namespace': 'test_namespace'}
            assert mock_send.call_args[0][2] == 'invalid_ph_no'
            assert mock_send.call_args[1] == {'messaging_type': 'template'}

    @pytest.mark.asyncio
    async def test_send_template_message_without_namespace(self, whatsapp_on_premise):
        name = "test_template_name"
        to_phone_number = "invalid_ph_no"
        with patch("kairon.chat.handlers.channels.clients.whatsapp.on_premise.WhatsappOnPremise.send",
                   autospec=True) as mock_send:
            mock_send.return_value = {"error": {"message": "to_phone_number is not valid", "code": 400}}

            with pytest.raises(AppException, match="namespace is required to send messages using on-premises api!"):
                await whatsapp_on_premise.send_template_message(name=name, to_phone_number=to_phone_number)


class TestWhatsappCloud:

    @pytest.fixture(scope="module")
    def whatsapp_cloud(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(False)
        from_phone_number_id = "918958030415"
        whatsapp_cloud = WhatsappCloud(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        yield whatsapp_cloud

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_action(self, whatsapp_cloud, aioresponses):
        body = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '9876543210', 'type': 'template', 'template': {'language': {'code': 'en'}, 'name': 'test_template_name', 'components': {'type': 'body', 'parameters': [{'type': 'text', 'text': 'text-string'}, {'type': 'currency', 'currency': {'fallback_value': 'VALUE', 'code': 'USD', 'amount_1000': '1000'}}, {'type': 'date_time', 'date_time': {'fallback_value': 'DATE'}}]}}}
        aioresponses.post(
            url="https://graph.facebook.com/v13.0/918958030415/messages",
            status=200,
            headers=whatsapp_cloud.auth_args,
            payload={
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]},
        )
        response = await whatsapp_cloud.send_action(payload=body)
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '9876543210', 'type': 'template', 'template': {'language': {'code': 'en'}, 'name': 'test_template_name', 'components': {'type': 'body', 'parameters': [{'type': 'text', 'text': 'text-string'}, {'type': 'currency', 'currency': {'fallback_value': 'VALUE', 'code': 'USD', 'amount_1000': '1000'}}, {'type': 'date_time', 'date_time': {'fallback_value': 'DATE'}}]}}}
        assert response == '{"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_action(self, whatsapp_cloud, aioresponses):
        body = {'language': {'code': 'en'}, 'name': 'test_template_name', 'components': {'type': 'body', 'parameters': [{'type': 'text', 'text': 'text-string'}, {'type': 'currency', 'currency': {'fallback_value': 'VALUE', 'code': 'USD', 'amount_1000': '1000'}}, {'type': 'date_time', 'date_time': {'fallback_value': 'DATE'}}]}}
        aioresponses.post(
            url="https://graph.facebook.com/v13.0/918958030415/messages",
            status=200,
            headers=whatsapp_cloud.auth_args,
            payload={
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]},
        )
        response = await whatsapp_cloud.send_json(payload=body, to_phone_number="9876543210")
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'language': {'code': 'en'}, 'name': 'test_template_name', 'components': {'type': 'body', 'parameters': [{'type': 'text', 'text': 'text-string'}, {'type': 'currency', 'currency': {'fallback_value': 'VALUE', 'code': 'USD', 'amount_1000': '1000'}}, {'type': 'date_time', 'date_time': {'fallback_value': 'DATE'}}]}, 'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '9876543210'}
        assert response == '{"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_template_message(self, whatsapp_cloud, aioresponses):
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
        aioresponses.post(
            url="https://graph.facebook.com/v13.0/918958030415/messages",
            status=200,
            headers=whatsapp_cloud.auth_args,
            payload={
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]},
        )
        response = await whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                              components=components)
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '9876543210', 'type': 'template', 'template': {'language': {'code': 'en'}, 'name': 'test_template_name', 'components': {'type': 'body', 'parameters': [{'type': 'text', 'text': 'text-string'}, {'type': 'currency', 'currency': {'fallback_value': 'VALUE', 'code': 'USD', 'amount_1000': '1000'}}, {'type': 'date_time', 'date_time': {'fallback_value': 'DATE'}}]}}}
        assert response == '{"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_template_message_without_payload(self, whatsapp_cloud, aioresponses):
        name = "test_template_name"
        to_phone_number = "9876543210"
        aioresponses.post(
            url="https://graph.facebook.com/v13.0/918958030415/messages",
            status=200,
            headers=whatsapp_cloud.auth_args,
            payload={
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]},
        )
        response = await whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number)
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '9876543210', 'type': 'template', 'template': {'language': {'code': 'en'}, 'name': 'test_template_name'}}
        assert response == '{"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_template_message_with_namespace(self, whatsapp_cloud, aioresponses):
        namespace = "test_namespace"
        name = "test_template_name"
        to_phone_number = "9876543210"
        aioresponses.post(
            url="https://graph.facebook.com/v13.0/918958030415/messages",
            status=200,
            headers=whatsapp_cloud.auth_args,
            payload={
                "contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]},
        )
        response = await whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                            namespace=namespace)
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '9876543210', 'type': 'template', 'template': {'language': {'code': 'en'}, 'name': 'test_template_name'}}
        assert response == '{"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_template_message_failure(self, whatsapp_cloud, aioresponses):
        name = "test_template_name"
        to_phone_number = "invalid_ph_no"
        aioresponses.post(
            url="https://graph.facebook.com/v13.0/918958030415/messages",
            headers=whatsapp_cloud.auth_args,
            payload={"error": {"message": "to_phone_number is not valid", "code": 400}}
        )
        response = await whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number)
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': 'invalid_ph_no', 'type': 'template', 'template': {'language': {'code': 'en'}, 'name': 'test_template_name'}}
        assert response == '{"error": {"message": "to_phone_number is not valid", "code": 400}}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_get_attachment(self, whatsapp_cloud, aioresponses):
        aioresponses.get(
            'https://graph.facebook.com/v13.0/test_media_id',
            payload={"type": "document", "media_id": "test_media_id"},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_cloud.get_attachment(attachment_id="test_media_id")
        assert response == '{"type": "document", "media_id": "test_media_id"}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_get_attachment_failure(self, whatsapp_cloud, aioresponses):
        aioresponses.get(
            'https://graph.facebook.com/v13.0/invalid_id',
            payload={"error": {"message": "media_id is not valid", "code": 400}},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_cloud.get_attachment(attachment_id="invalid_id")
        assert response == '{"error": {"message": "media_id is not valid", "code": 400}}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_mark_as_read(self, whatsapp_cloud, aioresponses):
        aioresponses.post(
            'https://graph.facebook.com/v13.0/918958030415/messages',
            payload={"id": "test_msg_id"},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_cloud.mark_as_read(msg_id="test_msg_id")
        assert response == '{"id": "test_msg_id"}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'status': 'read', 'message_id': 'test_msg_id'}

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_mark_as_read_failure(self, whatsapp_cloud, aioresponses):
        aioresponses.post(
            'https://graph.facebook.com/v13.0/918958030415/messages',
            payload={"error": {"message": "msg_id is not valid", "code": 400}},
            status=200,
            content_type='application/json'
        )
        response = await whatsapp_cloud.mark_as_read(msg_id="invalid_id")
        assert response == '{"error": {"message": "msg_id is not valid", "code": 400}}'
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'access_token': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'status': 'read', 'message_id': 'invalid_id'}

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_template_message_with_360dialog(self, aioresponses):
        name = "test_template_name"
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(True)
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

        aioresponses.add(
            url='https://waba-v2.360dialog.io/messages',
            method="POST",
            status=200,
            headers={'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'},
            payload={"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        response = await whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                        components=components)
        assert list(aioresponses.requests.values())[0][0][1]['headers'] == {'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'}
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': '9876543210', 'type': 'template', 'template': {'language': {'code': 'en'}, 'name': 'test_template_name', 'components': {'type': 'body', 'parameters': [{'type': 'text', 'text': 'text-string'}, {'type': 'currency', 'currency': {'fallback_value': 'VALUE', 'code': 'USD', 'amount_1000': '1000'}}, {'type': 'date_time', 'date_time': {'fallback_value': 'DATE'}}]}}}
        assert response == '{"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_mark_read_360dialog(self, aioresponses):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(True)
        from_phone_number_id = "918958030415"
        aioresponses.add(
            url='https://waba-v2.360dialog.io/messages',
            method="POST",
            status=200,
            headers={'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'},
            payload={"success": True}
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        response = await whatsapp_cloud.mark_as_read("ASDFHJKJT")
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp', 'status': 'read', 'message_id': 'ASDFHJKJT'}
        assert response == '{"success": true}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_template_message_with_360dialog_failure(self, aioresponses):
        name = "test_template_name"
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(True)
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

        aioresponses.add(
            url='https://waba-v2.360dialog.io/messages',
            method="POST",
            headers={'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'},
            payload=error_msg
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        response = await whatsapp_cloud.send_template_message(name=name, to_phone_number=to_phone_number,
                                                        components=components)
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp',
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
                                                                                                'fallback_value': 'DATE'}}]}}}
        assert response == '{"error": {"message": "(#131009) Parameter value is not valid", "type": "OAuthException", "code": 131009, "error_data": {"messaging_product": "whatsapp", "details": "Please check the parameters you have provided."}, "error_subcode": 2494010, "fbtrace_id": "A_lIoKUKB2unS85jgB4Gl7B"}}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_mark_read_360dialog_failure(self, aioresponses):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(True)
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

        aioresponses.add(
            url='https://waba-v2.360dialog.io/messages',
            method="POST",
            headers={'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'},
            payload=error_msg
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        response = await whatsapp_cloud.mark_as_read("ASDFHJKJT")
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {'messaging_product': 'whatsapp',
                                                                         'status': 'read', 'message_id': 'ASDFHJKJT'}
        assert response == '{"error": {"message": "(#131009) Parameter value is not valid", "type": "OAuthException", "code": 131009, "error_data": {"messaging_product": "whatsapp", "details": "Please check the message ID you have provided."}, "error_subcode": 2494010, "fbtrace_id": "A_lIoKUKB2unS85jgB4Gl7B"}}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_message_with_360dialog(self, aioresponses):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(True)
        from_phone_number_id = "918958030415"
        to_phone_number = "9876543210"
        payload = {
            "preview_url": True,
            "body": "You have to check out this amazing messaging service https://www.whatsapp.com/"
        }

        aioresponses.add(
            url='https://waba-v2.360dialog.io/messages',
            method="POST",
            status=200,
            headers={'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'},
            payload={"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        response = await whatsapp_cloud.send(payload, to_phone_number, "text")
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {
                'messaging_product': "whatsapp",
                'recipient_type': "individual",
                "to": to_phone_number,
                "type": "text",
                "text": payload
            }
        assert response == '{"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}'

    @pytest.mark.asyncio
    async def test_whatsapp_cloud_send_message_with_360dialog_failure(self, aioresponses):
        access_token = "ERTYUIEFDGHGFHJKLFGHJKGHJ"
        session = AioRestClient(True)
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

        aioresponses.add(
            url='https://waba-v2.360dialog.io/messages',
            method="POST",
            headers={'D360-API-KEY': 'ERTYUIEFDGHGFHJKLFGHJKGHJ'},
            payload=error_msg
        )
        whatsapp_cloud = BSP360Dialog(access_token=access_token, session=session, from_phone_number_id=from_phone_number_id)
        response = await whatsapp_cloud.send(payload, to_phone_number, "text")
        assert list(aioresponses.requests.values())[0][0][1]['json'] == {
                'messaging_product': "whatsapp",
                'recipient_type': "individual",
                "to": to_phone_number,
                "type": "text",
                "text": payload
            }
        assert response == '{"error": {"message": "(#131009) Parameter value is not valid", "type": "OAuthException", "code": 131009, "error_data": {"messaging_product": "whatsapp", "details": "Please check the message ID you have provided."}, "error_subcode": 2494010, "fbtrace_id": "A_lIoKUKB2unS85jgB4Gl7B"}}'
