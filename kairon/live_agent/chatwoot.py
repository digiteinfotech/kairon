from typing import Text, List
from urllib.parse import urljoin

from kairon import Utility
from kairon.exceptions import AppException
from kairon.live_agent.live_agent import LiveAgent
from kairon.shared.live_agent.processor import LiveAgentsProcessor


class ChatwootLiveAgent(LiveAgent):

    def __init__(self, api_access_token: Text, account_id: int, inbox_identifier: Text = None):
        """
        Constructor for ChatwootLiveAgent.

        :param api_access_token: chatwoot user api access token
        :param account_id: chatwoot account id
        :param inbox_identifier: chatwoot inbox identifier. None, by default.
        """
        self.api_access_token = api_access_token
        self.account_id = account_id
        self.inbox_identifier = inbox_identifier

    @classmethod
    def from_config(cls, config: dict) -> "ChatwootLiveAgent":
        """
        Create ChatwootLiveAgent from saved config.
        """
        return cls(config["api_access_token"], config["account_id"], config.get("inbox_identifier"))

    @property
    def agent_type(self) -> str:
        return "chatwoot"

    @property
    def base_url(self) -> str:
        return "https://app.chatwoot.com/public/api/v1/"

    @property
    def create_conversation_endpoint(self) -> str:
        """
        Property to return create chatwoot conversation endpoint.
        """
        return urljoin(self.base_url, "inboxes/{inbox_identifier}/contacts/{contact_identifier}/conversations")

    @property
    def send_message_endpoint(self) -> str:
        """
        Property to return create chatwoot message endpoint.
        """
        return urljoin(self.base_url, "accounts/{account_id}/conversations/{conversation_id}/messages")

    @property
    def inboxes_endpoint(self) -> str:
        """
        Property to return create chatwoot inbox endpoint.
        """
        return urljoin(self.base_url, "accounts/{account_id}/inboxes")

    @property
    def add_contact_endpoint(self) -> str:
        """
        Property to return create chatwoot contact endpoint.
        """
        return urljoin(self.base_url, "inboxes/{inbox_identifier}/contacts")

    def complete_prerequisites(self, **kwargs):
        """
        Completes all prerequisites for live agent system before a user can be added.
        In case of chatwoot, an inbox should be present.
        This method creates an inbox if no prevalidated inbox exists.
        Same is returned from the method.

        :param kwargs: bot_name and bot id are required to create an inbox with that name.
        """
        bot_name = kwargs.get("bot_name")
        bot_id = kwargs.get("_id")
        if Utility.check_empty_string(self.inbox_identifier):
            inbox_info = self.create_inbox(f"kairon-{bot_name}-{bot_id}")
            self.inbox_identifier = inbox_info['inbox_identifier']
        return {"inbox_identifier": self.inbox_identifier}

    def initiate_handoff(self, bot: Text, sender_id: Text):
        """
        Steps required to be performed before a user can start communicating with the agent.
        In case of chatwoot, the contact identifier should exist. If not, then it is created.
        Then, a conversation is created for that particular user so that all messages by that
        user are logged into that conversation.

        :param bot: bot id
        :param sender_id: sender id of the end user
        :return: dict containing destination and pubsub_token obtained for that particular sender from chatwoot.
        """
        contact_info = LiveAgentsProcessor.get_contact(bot, sender_id, self.agent_type)
        if not contact_info:
            contact_info = self.create_contact(sender_id)
            LiveAgentsProcessor.save_contact(bot, sender_id, self.agent_type, contact_info)
        else:
            contact_info = contact_info["metadata"]
        conversation_info = self.create_conversation(contact_info["source_id"])
        return {"destination": conversation_info["id"], "pubsub_token": contact_info["pubsub_token"]}

    def send_message(self, message: Text, destination: Text, **kwargs):
        """
        Sends user message to the agent.
        Incoming message is the message from end user and outcoming message is the message from the agent.
        Raises exception if response status_code is not 200.

        :param message: message to be sent to the end user.
        :param destination: conversation id that was created for the user.
        :param kwargs: message_type(incoming/outgoing) of the message. incoming by default.
        :return: api response
        """
        headers = {"api_access_token": self.api_access_token}
        msg_type = kwargs.get("message_type")
        msg_type = msg_type if msg_type in {"incoming", "outgoing"} else "incoming"
        request_body = {"content": message, "message_type": msg_type}
        url = self.send_message_endpoint.format(account_id=self.account_id, conversation_id=destination)
        return Utility.execute_http_request(
            "POST", url, request_body, headers, validate_status=True, err_msg="Failed to send message: "
        )

    def send_conversation_log(self, messages: List, destination: Text):
        """
        Send complete conversation log between bot and the end user.
        Incoming message is the message from end user and outcoming message is the message from the agent.
        Messages of type bot are sent as outgoing message and messages from end user are sent as incoming message.

        :param messages: list of messages between end user and bot.
        :param destination: conversation id that was created for the sender.
        """
        for msg in messages:
            msg_type = None
            if msg.get('bot'):
                msg_type = "outgoing"
                msg = msg['bot']
            elif msg.get('user'):
                msg_type = "incoming"
                msg = msg['user']
            self.send_message(msg, destination, message_type=msg_type)

    def validate_credentials(self):
        """
        Validates whether credentials supplied by user are valid.
        In case of chatwoot, this is verified by listing the inboxes. Successful api call would
        mean that the credentials are valid.
        Also, if the user has supplied inbox identifier, then it is retrieved from the list inboxes response.
        If an inbox_identifier was supplied but it is not found in response, that would also
        mean that the credentials are invalid.
        """
        try:
            if not Utility.check_empty_string(self.inbox_identifier):
                self.get_inbox()
            self.list_inbox()
        except AppException:
            raise AppException("Unable to connect. Please verify credentials.")

    def create_contact(self, sender_id: Text):
        """
        Creates a contact in chatwoot for the end user.
        Raises exception if response status_code is not 200.

        :param sender_id: end user name or identifier
        :return: api response
        """
        headers = {"api_access_token": self.api_access_token}
        request_body = {"name": sender_id}
        url = self.add_contact_endpoint.format(inbox_identifier=self.inbox_identifier)
        return Utility.execute_http_request(
            "POST", url, request_body, headers, validate_status=True, err_msg="Failed to create contact: "
        )

    def list_inbox(self):
        """
        Lists inboxes for the account.
        Raises exception if response status_code is not 200.

        :return: api response
        """
        headers = {"api_access_token": self.api_access_token}
        url = self.inboxes_endpoint.format(account_id=self.account_id)
        return Utility.execute_http_request(
            "GET", url, headers=headers, validate_status=True, err_msg="Failed to list inbox: "
        )

    def get_inbox(self):
        """
        Retrieves all inboxes in account and searches for the supplied inbox identifier in that list.
        Raises exception if inbox identifier not found in the list of inboxes.

        :return: inbox details
        """
        inboxes = self.list_inbox()
        for inbox in inboxes.get("payload", []):
            if inbox['inbox_identifier'] == self.inbox_identifier:
                return inbox
        raise AppException(f"Inbox with identifier {self.inbox_identifier} does not exists!")

    def create_inbox(self, name: Text):
        """
        Creates inbox with the name supplied.
        Raises exception if response status_code is not 200.

        :param name: name of the inbox
        :return: api response
        """
        headers = {"api_access_token": self.api_access_token}
        request_body = {"name": name, "channel": {"type": "api"}}
        url = self.inboxes_endpoint.format(account_id=self.account_id)
        return Utility.execute_http_request(
            "POST", url, request_body, headers, validate_status=True, err_msg="Failed to create inbox: "
        )

    def create_conversation(self, contact_identifier: Text):
        """
        Creates new conversation for a contact.
        Raises exception if response status_code is not 200.
        Just FYI,
            inbox_id != inbox_identifier
            contact_id != contact_identifier

        :param contact_identifier: contact identifier of contact for which conversation needs to be created.
        :return: api response
        """
        headers = {"api_access_token": self.api_access_token}
        url = self.create_conversation_endpoint.format(
            inbox_identifier=self.inbox_identifier, contact_identifier=contact_identifier
        )
        return Utility.execute_http_request(
            "POST", url, headers=headers, validate_status=True, err_msg="Failed to create conversation: "
        )
