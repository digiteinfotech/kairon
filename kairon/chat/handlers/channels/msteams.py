import datetime
import json
import re
from http import HTTPStatus
from typing import Text, Dict, Any, List, Iterable, Optional

import jwt
import requests
from jwt import InvalidKeyError, PyJWTError
from jwt.algorithms import RSAAlgorithm
from loguru import logger
from rasa.core.channels.channel import UserMessage, OutputChannel, InputChannel
from sanic import response
from sanic.response import HTTPResponse
from tornado.escape import json_encode

from kairon import Utility
from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.converters.channels.constants import CHANNEL_TYPES
from kairon.chat.converters.channels.response_factory import ConverterFactory
from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.tornado.handlers.base import BaseHandler



class MSTeamBot(OutputChannel):
    """A Microsoft Bot Framework communication channel."""
    token_expiration_date = datetime.datetime.now()
    BEARER_REGEX = re.compile(r"Bearer\s+(.*)")

    headers = None

    @classmethod
    def name(cls) -> Text:
        return "botframework"

    def __init__(
        self,
        app_id: Text,
        app_password: Text,
        conversation: Dict[Text, Any],
        bot: Text,
        service_url: Text,
    ) -> None:

        service_url = ( f"{service_url}/" if not service_url.endswith("/") else service_url)
        self.app_id = app_id
        self.app_password = app_password
        self.conversation = conversation
        self.global_uri = f"{service_url}v3/"
        self.bot = bot

    async def _get_headers(self, refetch=False) -> Optional[Dict[Text, Any]]:
        ms_oauthurl = ElementTransformerOps.getChannelConfig("msteams", "MICROSOFT_OAUTH2_URL")
        ms_oauthpath = ElementTransformerOps.getChannelConfig("msteams", "MICROSOFT_OAUTH2_PATH")
        scope = ElementTransformerOps.getChannelConfig("msteams", "scope")
        if MSTeamBot.token_expiration_date < datetime.datetime.now() or refetch:
            uri = f"{ms_oauthurl}/{ms_oauthpath}"
            grant_type = "client_credentials"
            payload = {
                'client_id': self.app_id,
                'client_secret': self.app_password,
                'grant_type': grant_type,
                'scope': scope,
            }

            token_response = requests.post(uri, data=payload)

            if token_response.ok:
                token_data = token_response.json()
                access_token = token_data["access_token"]
                token_expiration = token_data["expires_in"]

                delta = datetime.timedelta(seconds=int(token_expiration))
                MSTeamBot.token_expiration_date = datetime.datetime.now() + delta

                MSTeamBot.headers = {
                    "content-type": "application/json",
                    "Authorization": "Bearer %s" % access_token,
                }
                return MSTeamBot.headers
            else:
                logger.error("Could not get BotFramework token")
                return None
        else:
            return MSTeamBot.headers

    def prepare_message(
        self, recipient_id: Text, message_data: Dict[Text, Any]
    ) -> Dict[Text, Any]:
        data = {
            "type": "message",
            "recipient": {"id": recipient_id},
            "from": self.bot,
            "channelData": {"notification": {"alert": "true"}},
            "text": "",
        }
        data.update(message_data)
        return data

    async def send(self, message_data: Dict[Text, Any]) -> None:
        post_message_uri = "{}conversations/{}/activities".format(
            self.global_uri, self.conversation["id"]
        )
        headers = await self._get_headers()
        send_response = requests.post(
            post_message_uri,headers=headers, data=json.dumps(message_data)
        )

        if send_response.status_code == 403:
            headers = await self._get_headers(True)
            send_response = requests.post(
                post_message_uri, headers=headers, data=json.dumps(message_data)
            )

        if not send_response.ok:
            logger.error(
                "Error trying to send botframework messge. Response: %s",
                send_response.text,
            )
            raise Exception(f"Exception while responding to MSTeams:: {send_response.text} and status::{send_response.status_code}")


    async def send_text_message(
        self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        for message_part in text.strip().split("\n\n"):
            text_message = {"text": message_part}
            message = self.prepare_message(recipient_id, text_message)
            await self.send(message)

    async def send_image_url(
        self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        hero_content = {
            "contentType": "application/vnd.microsoft.card.hero",
            "content": {"images": [{"url": image}]},
        }

        image_message = {"attachments": [hero_content]}
        message = self.prepare_message(recipient_id, image_message)
        await self.send(message)

    async def send_text_with_buttons(
        self,
        recipient_id: Text,
        text: Text,
        buttons: List[Dict[Text, Any]],
        **kwargs: Any,
    ) -> None:
        hero_content = {
            "contentType": "application/vnd.microsoft.card.hero",
            "content": {"subtitle": text, "buttons": buttons},
        }

        buttons_message = {"attachments": [hero_content]}
        message = self.prepare_message(recipient_id, buttons_message)
        await self.send(message)

    async def send_elements(
        self, recipient_id: Text, elements: Iterable[Dict[Text, Any]], **kwargs: Any
    ) -> None:
        for e in elements:
            message = self.prepare_message(recipient_id, e)
            await self.send(message)

    async def send_custom_json(
        self, recipient_id: Text, json_message: Dict[Text, Any], **kwargs: Any
    ) -> None:
        try:
            message = json_message.get("data")
            message_type = json_message.get("type")
            type_list = Utility.system_metadata.get("type_list")
            if message_type is not None and message_type in type_list:
                converter_instance = ConverterFactory.getConcreteInstance(message_type, CHANNEL_TYPES.MSTEAMS.value)
                response = await converter_instance.messageConverter(message)
                data = {
                    "type": "message",
                    "recipient": {"id": recipient_id},
                    "from": self.bot,
                    "channelData": {"notification": {"alert": "true"}},
                    "text": "",
                }
                data.update(response)
                await self.send(data)
            else:
                await self.send({"text": str(json_message)})
        except Exception as ap:
            raise Exception(f"Error in msteams send_custom_json {str(ap)}")


class MSTeamsHandler(InputChannel, BaseHandler):
    """Bot Framework input channel implementation."""

    @classmethod
    def name(cls) -> Text:
        return "botframework"

    @classmethod
    def from_credentials(cls, credentials: Optional[Dict[Text, Any]]) -> InputChannel:
        if not credentials:
            cls.raise_missing_credentials_exception()

        return cls(credentials.get("app_id"), credentials.get("app_password"))

    def _update_cached_jwk_keys(self) -> None:
        try:
            ms_openid = ElementTransformerOps.getChannelConfig("msteams", "MICROSOFT_OPEN_ID_URI")
            response = requests.get(ms_openid)
            response.raise_for_status()
            conf = response.json()

            jwks_uri = conf["jwks_uri"]

            keys_request = requests.get(jwks_uri)
            keys_request.raise_for_status()
            keys_list = keys_request.json()
            self.jwt_keys = {key["kid"]: key for key in keys_list["keys"]}
            self.jwt_update_time = datetime.datetime.now()
        except Exception as ex:
            raise Exception(f"Exception while fetching jwks-keys from {ms_openid}, error as:: {ex}")

    def _validate_jwt_token(self, jwt_token: Text, app_id) -> None:
        jwt_header = jwt.get_unverified_header(jwt_token)
        key_id = jwt_header["kid"]
        if key_id not in self.jwt_keys:
            raise InvalidKeyError(f"JWT Key with ID {key_id} not found in Initialized list of keys.")

        key_json = self.jwt_keys[key_id]
        public_key = RSAAlgorithm.from_jwk(key_json)  # type: ignore
        try:
            jwt.decode(
                jwt_token,
                key=public_key,
                audience= app_id,
                algorithms=jwt_header["alg"],
            )
        except PyJWTError as ex:
            raise PyJWTError(f"Exception in jwt token authentication :: {str(ex)}")

    def _validate_auth(self, auth_header: Optional[Text], app_id: Text) -> Optional[HTTPResponse]:
        if not auth_header:
            return response.text(
                "No authorization header provided.", status=HTTPStatus.UNAUTHORIZED
            )
        # Update the JWT keys daily
        if datetime.datetime.now() - self.jwt_update_time > datetime.timedelta(days=1):
            try:
                self._update_cached_jwk_keys()
            except Exception as error:
                logger.warning(
                    f"Could not update JWT keys {error} "
                )
                logger.exception(error, exc_info=True)

        auth_match = MSTeamBot.BEARER_REGEX.match(auth_header)
        if not auth_match:
            return response.text(
                "No Bearer token provided in Authorization header.",
                status=HTTPStatus.UNAUTHORIZED,
            )

        (jwt_token,) = auth_match.groups()

        try:
            self._validate_jwt_token(jwt_token, app_id)
        except PyJWTError as error:
            logger.error(f"MSTeamsHandler framework JWT token could not be verified::{str(error)}")
            return response.text(
                "Could not validate JWT token.", status=HTTPStatus.UNAUTHORIZED
            )
        return None

    @staticmethod
    def add_attachments_to_metadata(
        postdata: Dict[Text, Any], metadata: Optional[Dict[Text, Any]]
    ) -> Optional[Dict[Text, Any]]:
        """Merge the values of `postdata['attachments']` with `metadata`."""
        if postdata.get("attachments"):
            attachments = {"attachments": postdata["attachments"]}
            if metadata:
                metadata.update(attachments)
            else:
                metadata = attachments
        return metadata

    async def get(self, bot: str, test: int) :
        return self.write(json_encode({"status": "ok"}))

    async def post(self, bot:str, token:str):
        try:
            logger.info(f"MSTeams chat initiation for bot {bot}")
            messenger_conf = ChatDataProcessor.get_channel_config("msteams", bot, mask_characters=False)
            hashed_token = messenger_conf["meta_config"]["secrethash"]
            if hashed_token == token:
                encrypted_token = messenger_conf["meta_config"]["secrettoken"]
            else:
                raise Exception("Webhook url is not updated, please check. Url on msteams still refer old hashtoken")
            user_auth_token = Utility.decrypt_message(encrypted_token)
            app_id = messenger_conf["config"]["app_id"]
            app_password = messenger_conf["config"]["app_secret"]
            super().authenticate_channel(user_auth_token, bot, self.request)
            self._update_cached_jwk_keys()
            validation_response = self._validate_auth(
                self.request.headers.get("Authorization"), app_id
            )
            if validation_response:
                return validation_response

            postdata = json.loads(self.request.body)
            metadata = self.get_metadata(self.request)
            metadata_with_attachments = self.add_attachments_to_metadata(
                postdata, metadata
            )

            if postdata["type"] == "message":
                out_channel = MSTeamBot(app_id, app_password, postdata["conversation"], postdata["recipient"],
                    postdata["serviceUrl"],)

                user_msg = UserMessage(text=postdata.get("text", ""), output_channel=out_channel, sender_id=postdata["from"]["id"],
                    input_channel=self.name(), metadata=metadata_with_attachments,)
                await AgentProcessor.get_agent(bot).handle_message(user_msg)
            else:
                logger.info("Not received message type")
        except Exception as ex:
            logger.error(f"Exception MSTeams post method:: {ex}")
        return response.text("success")