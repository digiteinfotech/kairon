import hashlib
import hmac
import json
import logging
import re
import time
from abc import ABC
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Text
from urllib.parse import parse_qs

import rasa.shared.utils.io
from rasa.core.channels.channel import InputChannel, OutputChannel, UserMessage
from slack import WebClient
from tornado.escape import json_decode
from tornado.httputil import HTTPServerRequest

from kairon.chat.agent_processor import AgentProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.tornado.handlers.base import BaseHandler
from kairon import Utility
from kairon.chat.converters.channels.response_factory import ConverterFactory
from kairon.chat.converters.channels.constants import CHANNEL_TYPES


logger = logging.getLogger(__name__)


class SlackBot(OutputChannel):
    """A Slack communication channel"""

    @classmethod
    def name(cls) -> Text:
        return "slack"

    def __init__(
            self,
            token: Text,
            slack_channel: Optional[Text] = None,
            thread_id: Optional[Text] = None,
            proxy: Optional[Text] = None,
    ) -> None:

        self.slack_channel = slack_channel
        self.thread_id = thread_id
        self.proxy = proxy
        self.client = WebClient(token, run_async=True, proxy=proxy)
        super().__init__()

    async def _post_message(self, channel: Text, **kwargs: Any) -> None:
        if self.thread_id:
            await self.client.chat_postMessage(
                channel=channel, **kwargs, thread_ts=self.thread_id
            )
        else:
            await self.client.chat_postMessage(channel=channel, **kwargs)

    async def send_text_message(
            self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        recipient = self.slack_channel or recipient_id
        for message_part in text.strip().split("\n\n"):
            await self._post_message(
                channel=recipient, as_user=True, text=message_part, type="mrkdwn"
            )

    async def send_image_url(
            self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        recipient = self.slack_channel or recipient_id
        image_block = {"type": "image", "image_url": image, "alt_text": image}

        await self._post_message(
            channel=recipient, as_user=True, text=image, blocks=[image_block]
        )

    async def send_attachment(
            self, recipient_id: Text, attachment: Dict[Text, Any], **kwargs: Any
    ) -> None:
        recipient = self.slack_channel or recipient_id
        await self._post_message(
            channel=recipient, as_user=True, attachments=[attachment], **kwargs
        )

    async def send_text_with_buttons(
            self,
            recipient_id: Text,
            text: Text,
            buttons: List[Dict[Text, Any]],
            **kwargs: Any,
    ) -> None:
        recipient = self.slack_channel or recipient_id

        text_block = {"type": "section", "text": {"type": "plain_text", "text": text}}

        if len(buttons) > 5:
            rasa.shared.utils.io.raise_warning(
                "Slack API currently allows only up to 5 buttons. "
                "Since you added more than 5, slack will ignore all of them."
            )
            return await self.send_text_message(recipient, text, **kwargs)

        button_block = {"type": "actions", "elements": []}
        for button in buttons:
            button_block["elements"].append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": button["title"]},
                    "value": button["payload"],
                }
            )

        await self._post_message(
            channel=recipient,
            as_user=True,
            text=text,
            blocks=[text_block, button_block],
        )

    async def send_custom_json(
            self, recipient_id: Text, json_message: Dict[Text, Any], **kwargs: Any
    ) -> None:
        try:
            message = json_message.get("data")
            message_type = json_message.get("type")
            type_list = Utility.system_metadata.get("type_list")

            if message_type is not None and message_type in type_list:
                converter_instance = ConverterFactory.getConcreteInstance(message_type, CHANNEL_TYPES.SLACK.value)
                response = await converter_instance.messageConverter(message)
                channel = json_message.get("channel", self.slack_channel or recipient_id)
                json_message.setdefault("as_user", True)
                await self._post_message(channel=channel, **response)
            else:
                channel = json_message.get("channel", self.slack_channel or recipient_id)
                await self._post_message(channel=channel, as_user=True, text=json_message, type="mrkdwn")
        except Exception as ap:
            raise Exception(f"Error in slack send_custom_json {str(ap)}")


class SlackHandler(InputChannel, BaseHandler, ABC):
    """Slack input channel implementation. Based on the HTTPInputChannel."""

    @staticmethod
    def _is_app_mention(slack_event: Dict) -> bool:
        try:
            return slack_event["event"]["type"] == "app_mention"
        except KeyError:
            return False

    @staticmethod
    def _is_direct_message(slack_event: Dict) -> bool:
        try:
            return slack_event["event"]["channel_type"] == "im"
        except KeyError:
            return False

    @staticmethod
    def _is_user_message(slack_event: Dict[Text, Any]) -> bool:
        return (
                slack_event.get("event") is not None
                and (
                        slack_event.get("event", {}).get("type") == "message"
                        or slack_event.get("event", {}).get("type") == "app_mention"
                )
                and slack_event.get("event", {}).get("text")
                and not slack_event.get("event", {}).get("bot_id")
        )

    @staticmethod
    def _sanitize_user_message(
            text: Text, uids_to_remove: Optional[List[Text]]
    ) -> Text:
        """Remove superfluous/wrong/problematic tokens from a message.

        Probably a good starting point for pre-formatting of user-provided text
        to make NLU's life easier in case they go funky to the power of extreme

        In the current state will just drop self-mentions of bot itself

        Args:
            text: raw message as sent from slack
            uids_to_remove: a list of user ids to remove from the content

        Returns:
            str: parsed and cleaned version of the input text
        """

        uids_to_remove = uids_to_remove or []

        for uid_to_remove in uids_to_remove:
            # heuristic to format majority cases OK
            # can be adjusted to taste later if needed,
            # but is a good first approximation
            for regex, replacement in [
                (fr"<@{uid_to_remove}>\s", ""),
                (fr"\s<@{uid_to_remove}>", ""),  # a bit arbitrary but probably OK
                (fr"<@{uid_to_remove}>", " "),
            ]:
                text = re.sub(regex, replacement, text)

        # Find multiple mailto or http links like
        # <mailto:xyz@rasa.com|xyz@rasa.com> or
        # <http://url.com|url.com> in text and substitute
        # it with original content
        pattern = r"(\<(?:mailto|http|https):\/\/.*?\|.*?\>)"
        match = re.findall(pattern, text)

        if match:
            for remove in match:
                replacement = remove.split("|")[1]
                replacement = replacement.replace(">", "")
                text = text.replace(remove, replacement)
        return text.strip()

    @staticmethod
    def _is_interactive_message(payload: Dict) -> bool:
        """Check wheter the input is a supported interactive input type."""

        supported = [
            "button",
            "select",
            "static_select",
            "external_select",
            "conversations_select",
            "users_select",
            "channels_select",
            "overflow",
            "datepicker",
        ]
        if payload.get("actions"):
            action_type = payload["actions"][0].get("type")
            if action_type in supported:
                return True
            elif action_type:
                logger.warning(
                    f"Received input from a Slack interactive component of type "
                    f"'{payload['actions'][0]['type']}', "
                    f"for which payload parsing is not yet supported."
                )
        return False

    @staticmethod
    def _get_interactive_response(action: Dict) -> Optional[Text]:
        """Parse the payload for the response value."""

        if action["type"] == "button":
            return action.get("value")
        elif action["type"] == "select":
            return action.get("selected_options", [{}])[0].get("value")
        elif action["type"] == "static_select":
            return action.get("selected_option", {}).get("value")
        elif action["type"] == "external_select":
            return action.get("selected_option", {}).get("value")
        elif action["type"] == "conversations_select":
            return action.get("selected_conversation")
        elif action["type"] == "users_select":
            return action.get("selected_user")
        elif action["type"] == "channels_select":
            return action.get("selected_channel")
        elif action["type"] == "overflow":
            return action.get("selected_option", {}).get("value")
        elif action["type"] == "datepicker":
            return action.get("selected_date")

    async def process_message(
            self,
            request: HTTPServerRequest,
            bot: Text,
            text: Text,
            sender_id: Optional[Text],
            metadata: Optional[Dict],
            slack_token: Text,
            use_threads: Optional[bool] = False,
    ) -> Any:
        """Slack retries to post messages up to 3 times based on
        failure conditions defined here:
        https://api.slack.com/events-api#failure_conditions
        """
        retry_reason = request.headers.get("X-Slack-Retry-Reason")
        retry_count = request.headers.get("X-Slack-Retry-Num")
        if retry_count and retry_reason in ["http_timeout"]:
            logger.warning(
                f"Received retry #{retry_count} request from slack"
                f" due to {retry_reason}."
            )
            self.set_status(HTTPStatus.CREATED)
            self.write('')
            self.set_header("X-Slack-No-Retry", 1)
        if metadata is not None:
            output_channel = metadata.get("out_channel")
            if use_threads:
                thread_id = metadata.get("thread_id")
            else:
                thread_id = None
        else:
            output_channel = None
            thread_id = None

        try:
            user_msg = UserMessage(
                text,
                self.get_output_channel(slack_token, channel=output_channel, thread_id=thread_id),
                sender_id,
                input_channel=self.name(),
                metadata=metadata,
            )
            await AgentProcessor.get_agent(bot).handle_message(user_msg)
        except Exception as e:
            logger.error(f"Exception when trying to handle message.{e}")
            logger.error(str(e), exc_info=True)
            self.write("")
        self.set_status(HTTPStatus.OK)

    def get_metadata(self, request: HTTPServerRequest) -> Dict[Text, Any]:
        """Extracts the metadata from a slack API event.

        Slack Documentation: https://api.slack.com/types/event

        Args:
            request: A `Request` object that contains a slack API event in the body.

        Returns:
            Metadata extracted from the sent event payload. This includes the output
                channel for the response, and users that have installed the bot.
        """
        content_type = request.headers.get("content-type")

        # Slack API sends either a JSON-encoded or a URL-encoded body depending on the
        # content
        if content_type == "application/json":
            # if JSON-encoded message is received
            slack_event = json_decode(request.body)
            event = slack_event.get("event", {})
            thread_id = event.get("thread_ts", event.get("ts"))

            users = []
            if "authed_users" in slack_event:
                users = slack_event.get("authed_users")
            elif (
                    "authorizations" in slack_event
                    and len(slack_event.get("authorizations")) > 0
            ):
                users.append(slack_event.get("authorizations")[0].get("user_id"))

            return {
                "out_channel": event.get("channel"),
                "thread_id": thread_id,
                "users": users,
            }

        if content_type == "application/x-www-form-urlencoded":
            # if URL-encoded message is received
            output = request.body
            payload = json.loads(output["payload"][0])
            message = payload.get("message", {})
            thread_id = message.get("thread_ts", message.get("ts"))

            users = []
            if payload.get("user", {}).get("id"):
                users.append(payload.get("user", {}).get("id"))

            return {
                "out_channel": payload.get("channel", {}).get("id"),
                "thread_id": thread_id,
                "users": users,
            }

        return {}

    def is_request_from_slack_authentic(self, request: HTTPServerRequest, slack_signing_secret: Text = "") -> bool:
        """Validate a request from Slack for its authenticity.

        Checks if the signature matches the one we expect from Slack. Ensures
        we don't process request from a third-party disguising as slack.

        Args:
            request: incoming request to be checked

        Returns:
            `True` if the request came from Slack.
            :param slack_signing_secret:
        """

        try:
            slack_signing_secret = bytes(slack_signing_secret, "utf-8")

            slack_signature = request.headers.get("X-Slack-Signature", "")
            slack_request_timestamp = request.headers.get(
                "X-Slack-Request-Timestamp", "0"
            )

            if abs(time.time() - int(slack_request_timestamp)) > 60 * 5:
                # The request timestamp is more than five minutes from local time.
                # It could be a replay attack, so let's ignore it.
                return False

            prefix = f"v0:{slack_request_timestamp}:".encode("utf-8")
            basestring = prefix + request.body
            digest = hmac.new(
                slack_signing_secret, basestring, hashlib.sha256
            ).hexdigest()
            computed_signature = f"v0={digest}"

            return hmac.compare_digest(computed_signature, slack_signature)
        except Exception as e:
            logger.error(
                f"Failed to validate slack request authenticity. "
                f"Assuming invalid request. Error: {e}"
            )
            return False

    def install_slack_to_workspace(self, bot: Text, token: Text, code: Text):
        user = super().authenticate_channel(token, bot, self.request)
        slack_config = ChatDataProcessor.get_channel_config("slack", bot, False, config__is_primary=True)
        client_id = slack_config['config']['client_id']
        client_secret = slack_config['config']['client_secret']
        response = WebClient().oauth_v2_access(
            client_id=client_id, client_secret=client_secret, code=code
        )
        if slack_config.get('_id'):
            del slack_config['_id']
        slack_config['config']['bot_user_oAuth_token'] = response.data['access_token']
        slack_config['config']['is_primary'] = False
        slack_config['config']['team'] = response.data['team']
        slack_config['connector_type'] = "slack"
        ChatDataProcessor.save_channel_config(slack_config, bot, user.get_user())
        self.redirect(f"https://app.slack.com/client/{response.data['team']['id']}")

    async def get(self, bot: Text = None, token: Text = None):
        code = self.get_argument('code', None)
        if not Utility.check_empty_string(bot) and not Utility.check_empty_string(token) and not Utility.check_empty_string(code):
            self.install_slack_to_workspace(bot, token, code)
            return
        self.set_status(HTTPStatus.OK)
        self.write(json.dumps({"status": "ok"}))

    async def post(self, bot: Text, token: Text):
        user = super().authenticate_channel(token, bot, self.request)
        content_type = self.request.headers.get("content-type")
        conversation_granularity = "sender"
        primary_slack_config = ChatDataProcessor.get_channel_config("slack", bot, False, config__is_primary=True)
        slack_signing_secret = primary_slack_config['config']['slack_signing_secret']
        slack_channel = primary_slack_config['config'].get('slack_channel')
        self.set_status(HTTPStatus.OK)
        if 'x-slack-retry-num' in self.request.headers:
            return
        if not self.is_request_from_slack_authentic(self.request, slack_signing_secret=slack_signing_secret):
            self.set_status(HTTPStatus.BAD_REQUEST)
            self.write("Message is not properly signed with a valid "
                       "X-Slack-Signature header")
            return
        # Slack API sends either a JSON-encoded or a URL-encoded body
        # depending on the content

        if content_type == "application/json":
            # if JSON-encoded message is received
            output = json_decode(self.request.body)
            event = output.get("event", {})
            user_message = event.get("text", "")
            sender_id = event.get("user", "")
            metadata = self.get_metadata(self.request) or {}
            metadata.update({"is_integration_user": True, "bot": bot, "account": user.account, "channel_type": "slack"})
            channel_id = metadata.get("out_channel")
            thread_id = metadata.get("thread_id")
            conversation_id = self._get_conversation_id(
                conversation_granularity, sender_id, channel_id, thread_id
            )

            if "challenge" in output:
                self.write(output.get("challenge"))
                return

            if not self._is_user_message(output):
                logger.debug(
                    "Received message from Slack which doesn't look like "
                    "a user message. Skipping message."
                )
                self.write("Bot message delivered.")
                return

            if not self._is_supported_channel(output, metadata, slack_channel):
                logger.warning(
                    f"Received message on unsupported "
                    f"channel: {metadata['out_channel']}"
                )
                self.write("channel not supported.")
                return

            slack_config = ChatDataProcessor.get_channel_config("slack", bot, False, config__team__id=output.get('team_id'))
            slack_token = slack_config['config']['bot_user_oAuth_token']
            await self.process_message(
                self.request,
                bot,
                text=self._sanitize_user_message(user_message, metadata["users"]),
                sender_id=conversation_id,
                metadata=metadata,
                slack_token=slack_token
            )
            return
        elif content_type == "application/x-www-form-urlencoded":
            # if URL-encoded message is received
            output = parse_qs(self.request.body)
            payload = json.loads(output["payload"][0])

            if self._is_interactive_message(payload):
                sender_id = payload["user"]["id"]
                text = self._get_interactive_response(payload["actions"][0])
                if text is not None:
                    metadata = self.get_metadata(self.request)
                    metadata.update({"sender_id": sender_id, "channel_type": "slack"})
                    channel_id = metadata.get("out_channel")
                    thread_id = metadata.get("thread_id")
                    conversation_id = self._get_conversation_id(
                        conversation_granularity, sender_id, channel_id, thread_id
                    )

                    slack_config = ChatDataProcessor.get_channel_config("slack", bot, False, config__team__id=output.get('team_id'))
                    slack_token = slack_config['config']['bot_user_oAuth_token']
                    await self.process_message(
                        self.request, bot, text, conversation_id, metadata, slack_token=slack_token
                    )
                    return
                if payload["actions"][0]["type"] == "button":
                    # link buttons don't have "value", don't send their clicks to
                    # bot
                    self.write("User clicked link button")
                    return
            self.set_status(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.write("The input message could not be processed.")
            return
        self.write("Bot message delivered.")
        return

    def _get_conversation_id(
            self,
            conversation_granularity,
            sender_id: Optional[Text],
            channel_id: Optional[Text],
            thread_id: Optional[Text],
    ) -> Optional[Text]:
        conversation_id = sender_id
        if conversation_granularity == "channel" and sender_id and channel_id:
            conversation_id = sender_id + "_" + channel_id
        if (
                conversation_granularity == "thread"
                and sender_id
                and channel_id
                and thread_id
        ):
            conversation_id = sender_id + "_" + channel_id + "_" + thread_id
        return conversation_id

    def _is_supported_channel(self, slack_event: Dict, metadata: Dict, slack_channel: Optional[Text] = None) -> bool:
        return (
                self._is_direct_message(slack_event)
                or self._is_app_mention(slack_event)
                or metadata["out_channel"] == slack_channel
        )

    def get_output_channel(
            self,
            slack_token,
            proxy: Optional[Text] = None,
            channel: Optional[Text] = None,
            thread_id: Optional[Text] = None
    ) -> OutputChannel:
        channel = channel or self.slack_channel
        return SlackBot(slack_token, channel, thread_id, proxy)

    def set_output_channel(self, channel: Text) -> None:
        self.slack_channel = channel
