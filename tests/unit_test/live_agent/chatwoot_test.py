import json
import os

import pytest
import responses
from mongoengine import connect

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.live_agent.chatwoot import ChatwootLiveAgent


class TestChatwootLiveAgent:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())

    @responses.activate
    def test_validate_credentials(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67"}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json={"payload": []}
        )
        agent = ChatwootLiveAgent.from_config(config)
        assert agent.agent_type == "chatwoot"
        assert not agent.validate_credentials()

    @responses.activate
    def test_validate_credentials_with_inbox_id(self):
        inboxes = open("tests/testing_data/live_agent/list_inboxes_response.json", 'r').read()
        inboxes = json.loads(inboxes)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67",
                  "inbox_identifier": inboxes["payload"][1]["inbox_identifier"]}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inboxes
        )
        assert not ChatwootLiveAgent.from_config(config).validate_credentials()

    @responses.activate
    def test_validate_credentials_with_invalid_inbox_id(self):
        inboxes = open("tests/testing_data/live_agent/list_inboxes_response.json", 'r').read()
        inboxes = json.loads(inboxes)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghjklty67"}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inboxes
        )
        with pytest.raises(AppException, match=f"Unable to connect. Please verify credentials."):
            ChatwootLiveAgent.from_config(config).validate_credentials()

    @responses.activate
    def test_validate_credentials_failure(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67"}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            status=404,
            body="Not found"
        )
        with pytest.raises(AppException, match="Unable to connect. Please verify credentials."):
            ChatwootLiveAgent.from_config(config).validate_credentials()

    @responses.activate
    def test_complete_prerequisites(self):
        inbox = open("tests/testing_data/live_agent/add_inbox_response.json", 'r').read()
        inbox = json.loads(inbox)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67"}
        responses.add(
            "POST",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inbox
        )
        metadata = ChatwootLiveAgent.from_config(config).complete_prerequisites(**{"bot_name": "test", "_id": "hello"})
        assert metadata["inbox_identifier"] == inbox["inbox_identifier"]

    @responses.activate
    def test_complete_prerequisites_inbox_identifier_exists(self):
        inbox = open("tests/testing_data/live_agent/add_inbox_response.json", 'r').read()
        inbox = json.loads(inbox)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67",
                  "inbox_identifier": inbox["inbox_identifier"]}
        responses.add(
            "POST",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inbox
        )
        metadata = ChatwootLiveAgent.from_config(config).complete_prerequisites(**{"bot_name": "test", "_id": "hello"})
        assert metadata["inbox_identifier"] == inbox["inbox_identifier"]

    @responses.activate
    def test_initiate_handoff(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts',
            json={
                "source_id": "09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71",
                "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
                "id": 16951464,
                "name": 'test@chat.com',
                "email": None
            }
        )
        responses.add(
            "POST",
            'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts/09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71/conversations',
            json={
                "id": 2,
                "inbox_id": 14036,
                "contact_last_seen_at": 0,
                "status": "open",
                "agent_last_seen_at": 0,
                "messages": [],
                "contact": {
                    "id": 16951464,
                    "name": "test@chat.com",
                    "email": None,
                    "phone_number": None,
                    "account_id": 69469,
                    "created_at": "2022-05-04T15:40:58.190Z",
                    "updated_at": "2022-05-04T15:40:58.190Z",
                    "additional_attributes": {},
                    "identifier": None,
                    "custom_attributes": {},
                    "last_activity_at": None,
                    "label_list": []
                }
            }
        )
        responses.add(
            "POST",
            'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
            json={
                "id": 7487848,
                "content": "hello",
                "inbox_id": 14036,
                "conversation_id": 2,
                "message_type": 0,
                "content_type": "text",
                "content_attributes": {},
                "created_at": 1651679560,
                "private": False,
                "source_id": None,
                "sender": {
                    "additional_attributes": {},
                    "custom_attributes": {},
                    "email": None,
                    "id": 16951464,
                    "identifier": None,
                    "name": "test@chat.com",
                    "phone_number": None,
                    "thumbnail": "",
                    "type": "contact"
                }
            }
        )
        metadata = ChatwootLiveAgent.from_config(config).initiate_handoff("test", "udit")
        assert metadata == {"destination": 2, "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
                            'websocket_url': 'wss://app.chatwoot.com/cable', 'inbox_id': 14036}

    @responses.activate
    def test_initiate_handoff_contact_exists(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts',
            json={
                "source_id": "09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71",
                "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
                "id": 16951464,
                "name": 'test@chat.com',
                "email": None
            }
        )
        responses.add(
            "POST",
            'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts/09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71/conversations',
            json={
                "id": 3,
                "inbox_id": 14036,
                "contact_last_seen_at": 0,
                "status": "open",
                "agent_last_seen_at": 0,
                "messages": [],
                "contact": {
                    "id": 16951464,
                    "name": "test@chat.com",
                    "email": None,
                    "phone_number": None,
                    "account_id": 69469,
                    "created_at": "2022-05-04T15:40:58.190Z",
                    "updated_at": "2022-05-04T15:40:58.190Z",
                    "additional_attributes": {},
                    "identifier": None,
                    "custom_attributes": {},
                    "last_activity_at": None,
                    "label_list": []
                }
            }
        )
        responses.add(
            "POST",
            'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
            json={
                "id": 7487848,
                "content": "hello",
                "inbox_id": 14036,
                "conversation_id": 2,
                "message_type": 0,
                "content_type": "text",
                "content_attributes": {},
                "created_at": 1651679560,
                "private": False,
                "source_id": None,
                "sender": {
                    "additional_attributes": {},
                    "custom_attributes": {},
                    "email": None,
                    "id": 16951464,
                    "identifier": None,
                    "name": "test@chat.com",
                    "phone_number": None,
                    "thumbnail": "",
                    "type": "contact"
                }
            }
        )
        metadata = ChatwootLiveAgent.from_config(config).initiate_handoff("test", "udit")
        assert metadata == {"destination": 3, "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
                            'websocket_url': 'wss://app.chatwoot.com/cable', 'inbox_id': 14036}

    @responses.activate
    def test_send_message(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        send_msg_response = {
            "id": 7487848,
            "content": "hello",
            "inbox_id": 14036,
            "conversation_id": 2,
            "message_type": 0,
            "content_type": "text",
            "content_attributes": {},
            "created_at": 1651679560,
            "private": False,
            "source_id": None,
            "sender": {
                "additional_attributes": {},
                "custom_attributes": {},
                "email": None,
                "id": 16951464,
                "identifier": None,
                "name": "test@chat.com",
                "phone_number": None,
                "thumbnail": "",
                "type": "contact"
            }}
        responses.add(
            "POST",
            'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
            json=send_msg_response
        )
        response = ChatwootLiveAgent.from_config(config).send_message("hello", "2")
        assert response == send_msg_response

    @responses.activate
    def test_send_message_failure(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST",
            'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
            status=404,
        )
        with pytest.raises(AppException, match="Failed to send message: Not Found"):
            ChatwootLiveAgent.from_config(config).send_message("hello", "2")

    @responses.activate
    def test_send_conversation_log(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST",
            'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
            json={
            "id": 7487848,
            "content": "hello",
            "inbox_id": 14036,
            "conversation_id": 2,
            "message_type": 0,
            "content_type": "text",
            "content_attributes": {},
            "created_at": 1651679560,
            "private": False,
            "source_id": None,
            "sender": {
                "additional_attributes": {},
                "custom_attributes": {},
                "email": None,
                "id": 16951464,
                "identifier": None,
                "name": "test@chat.com",
                "phone_number": None,
                "thumbnail": "",
                "type": "contact"
            }}
        )
        message_log = [{'user': 'Hi'}, {'bot': 'Hey! How are you?'}, {'user': 'who can i contact?'}, {'bot': "I'm sorry, I didn't quite understand that. Could you rephrase?"}]
        assert not ChatwootLiveAgent.from_config(config).send_conversation_log(message_log, "2")

    @responses.activate
    def test_send_conversation_log_failure(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST",
            'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
            status=404
        )
        message_log = [{'user': 'Hi'}, {'bot': 'Hey! How are you?'}, {'user': 'who can i contact?'},
                       {'bot': "I'm sorry, I didn't quite understand that. Could you rephrase?"}]
        with pytest.raises(AppException, match="Failed to send message: Not Found"):
            ChatwootLiveAgent.from_config(config).send_conversation_log(message_log, "2")

    @responses.activate
    def test_create_contact(self):
        expected_response = {
                "source_id": "09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71",
                "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
                "id": 16951464,
                "name": 'test@chat.com',
                "email": None
            }
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts',
            json=expected_response
        )
        response = ChatwootLiveAgent.from_config(config).create_contact("udit")
        assert response == expected_response

    @responses.activate
    def test_create_contact_failure(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts',
            status=404
        )
        with pytest.raises(AppException, match="Failed to create contact: Not Found"):
            ChatwootLiveAgent.from_config(config).create_contact("udit")

    @responses.activate
    def test_list_inbox(self):
        inboxes = open("tests/testing_data/live_agent/list_inboxes_response.json", 'r').read()
        inboxes = json.loads(inboxes)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67",
                  "inbox_identifier": inboxes["payload"][1]["inbox_identifier"]}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inboxes
        )
        resp = ChatwootLiveAgent.from_config(config).list_inbox()
        assert resp == inboxes

    @responses.activate
    def test_list_inbox_failure(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "sdfghjk678gfhjk"}
        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            status=404
        )
        with pytest.raises(AppException, match="Failed to list inbox: Not Found"):
            ChatwootLiveAgent.from_config(config).list_inbox()

    @responses.activate
    def test_get_inbox(self):
        inboxes = open("tests/testing_data/live_agent/list_inboxes_response.json", 'r').read()
        inboxes = json.loads(inboxes)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67",
                  "inbox_identifier": inboxes["payload"][1]["inbox_identifier"]}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inboxes
        )
        resp = ChatwootLiveAgent.from_config(config).get_inbox()
        assert resp == inboxes["payload"][1]

    @responses.activate
    def test_get_inbox_failure(self):
        inboxes = open("tests/testing_data/live_agent/list_inboxes_response.json", 'r').read()
        inboxes = json.loads(inboxes)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67",
                  "inbox_identifier": "asdfghjklty67"}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inboxes
        )
        with pytest.raises(AppException, match="Inbox with identifier asdfghjklty67 does not exists!"):
            ChatwootLiveAgent.from_config(config).get_inbox()

    @responses.activate
    def test_create_inbox(self):
        inbox = open("tests/testing_data/live_agent/add_inbox_response.json", 'r').read()
        inbox = json.loads(inbox)
        config = {"account_id": "12", "api_access_token": "asdfghjklty67"}
        responses.add(
            "POST",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            json=inbox
        )
        resp = ChatwootLiveAgent.from_config(config).create_inbox("test")
        assert resp == inbox

    @responses.activate
    def test_create_inbox_failure(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67"}
        responses.add(
            "POST",
            f"https://app.chatwoot.com/api/v1/accounts/{config['account_id']}/inboxes",
            status=404
        )
        with pytest.raises(AppException, match="Failed to create inbox: Not Found"):
            ChatwootLiveAgent.from_config(config).create_inbox("test")

    @responses.activate
    def test_create_conversation(self):
        create_conversation_resp = {
            "id": 3,
            "inbox_id": 14036,
            "contact_last_seen_at": 0,
            "status": "open",
            "agent_last_seen_at": 0,
            "messages": [],
            "contact": {
                "id": 16951464,
                "name": "test@chat.com",
                "email": None,
                "phone_number": None,
                "account_id": 69469,
                "created_at": "2022-05-04T15:40:58.190Z",
                "updated_at": "2022-05-04T15:40:58.190Z",
                "additional_attributes": {},
                "identifier": None,
                "custom_attributes": {},
                "last_activity_at": None,
                "label_list": []
            }
        }
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST",
            'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts/test/conversations',
            json=create_conversation_resp
        )
        resp = ChatwootLiveAgent.from_config(config).create_conversation("test")
        assert resp == create_conversation_resp

    @responses.activate
    def test_create_conversation_failure(self):
        config = {"account_id": "12", "api_access_token": "asdfghjklty67", "inbox_identifier": "asdfghj345890dfghj"}
        responses.add(
            "POST",
            'https://app.chatwoot.com/public/api/v1/inboxes/asdfghj345890dfghj/contacts/test/conversations',
            status=404
        )
        with pytest.raises(AppException, match="Failed to create conversation: Not Found"):
            ChatwootLiveAgent.from_config(config).create_conversation("test")
