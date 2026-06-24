import logging
from typing import List

from starlette.requests import Request
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from kairon.chat.handlers.channels.clients.voice.base import VoiceProviderBase
from kairon.exceptions import AppException
from kairon.shared.chat.data_objects import ChannelLogs

logger = logging.getLogger(__name__)


class TwilioVoiceProvider(VoiceProviderBase):

    def __init__(self, bot: str, config: dict):
        """
        Initialise provider from already-decrypted channel config.

        config is supplied by get_channel_config(mask_characters=False) which decrypts
        account_sid and auth_token before reaching this point. Do NOT decrypt here.

        :param bot: bot ID this provider is serving
        :param config: decrypted channel config dict
        """
        super().__init__(bot, config)
        self.account_sid = config["account_sid"]
        self.auth_token = config["auth_token"]
        self.phone_number = config["phone_number"]
        self.voice_type = config.get("voice_type", "Polly.Amy")
        self.speech_model = "default"
        self.enhanced = "false"
        self._validator = RequestValidator(self.auth_token)

    def validate_signature(self, request: Request, url: str, form_params: dict) -> bool:
        signature = request.headers.get("X-Twilio-Signature", "")
        return self._validator.validate(url, form_params, signature)

    def build_voice_response(self, messages: List[str], call_url: str) -> str:
        voice_response = VoiceResponse()
        gather = Gather(
            input="speech",
            action=call_url,
            actionOnEmptyResult=True,
            speechTimeout=self.config.get("speech_timeout", "auto"),
            speechModel=self.speech_model,
            enhanced=self.enhanced,
            language=self.config.get("language", "en-US"),
        )
        for i, msg in enumerate(messages):
            if i + 1 == len(messages):
                gather.say(msg, voice=self.voice_type)
                voice_response.append(gather)
            else:
                voice_response.say(msg, voice=self.voice_type)
                voice_response.pause(length=1)
        if not messages:
            voice_response.append(gather)
        return str(voice_response)

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
