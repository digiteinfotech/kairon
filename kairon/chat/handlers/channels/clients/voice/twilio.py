import logging

from starlette.requests import Request
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from kairon.exceptions import AppException
from kairon.chat.handlers.channels.clients.voice.base import VoiceProviderBase
from kairon.shared.chat.data_objects import ChannelLogs
from kairon.shared.utils import Utility

logger = logging.getLogger(__name__)


class TwilioVoiceProvider(VoiceProviderBase):

    def __init__(self, bot: str, config: dict):
        super().__init__(bot, config)
        self.account_sid = Utility.decrypt_message(config["account_sid"])
        self.auth_token = Utility.decrypt_message(config["auth_token"])
        self.phone_number = config["phone_number"]
        self.voice_type = config.get("voice_type", "Polly.Amy")
        self.voice_types = config.get("voice_types", [self.voice_type])
        self.process_url = config.get("process_url", "")
        self._validator = RequestValidator(self.auth_token)

    def validate_signature(self, request: Request, url: str, form_params: dict) -> bool:
        signature = request.headers.get("X-Twilio-Signature", "")
        return self._validator.validate(url, form_params, signature)

    async def handle_incoming_call(self, request: Request) -> str:
        welcome = self.config.get("welcomeMessage", "Hello! How are you?")
        response = VoiceResponse()

        gather = response.gather(
            input="speech",
            action=self.process_url,
            method="POST",
            speech_timeout="auto",
            language=self.config.get("language", "en-US"),
        )
        gather.say(welcome, voice=self.voice_type)
        return str(response)

    async def handle_call_processing(self, request: Request, bot: str, rasa_response: str) -> str:
        response = VoiceResponse()
        if rasa_response:
            response.say(rasa_response, voice=self.voice_type)
        gather = response.gather(
            input="speech",
            action=self.process_url,
            method="POST",
            speech_timeout="auto",
            language=self.config.get("language", "en-US"),
        )
        gather.say("Is there anything else I can help you with?", voice=self.voice_type)
        return str(response)

    async def handle_call_status(self, request: Request, bot: str) -> None:
        form = dict(await request.form())
        call_status = form.get("CallStatus", "unknown")
        call_sid = form.get("CallSid", "unknown")
        logger.info(f"Voice call status update — bot={bot}, CallSid={call_sid}, CallStatus={call_status}")
        ChannelLogs(
            type="voice",
            status=call_status,
            data=form,
            message_id=call_sid,
            bot=bot,
            user=self.config.get("user", "system"),
        ).save()

    def validate_config(self, config: dict) -> None:
        for field in ["account_sid", "auth_token", "phone_number"]:
            if field not in config:
                raise AppException(f"Missing required voice config field: {field}")
