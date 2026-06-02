import logging
from typing import List, Text

from fastapi import HTTPException
from rasa.core.channels.channel import InputChannel, OutputChannel, UserMessage
from starlette.requests import Request

from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.handlers.channels.base import ChannelHandlerBase
from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes
from kairon.shared.models import User

logger = logging.getLogger(__name__)


class VoiceOutput(OutputChannel):

    @classmethod
    def name(cls) -> Text:
        return ChannelTypes.VOICE.value

    def __init__(self):
        self._messages: list = []

    async def send_text_message(self, recipient_id: Text, text: Text, **kwargs):
        self._messages.append(text)

    async def send_text_with_buttons(self, recipient_id: Text, text: Text, buttons, **kwargs):
        self._messages.append(text)
        for b in buttons:
            self._messages.append(b["title"])

    async def send_image_url(self, recipient_id: Text, image: Text, **kwargs):
        pass

    async def send_attachment(self, recipient_id: Text, attachment: Text, **kwargs):
        pass

    async def send_custom_json(self, recipient_id: Text, json_message, **kwargs):
        text = json_message.get("text") or json_message.get("data", {}).get("text")
        if text:
            self._messages.append(text)

    def get_accumulated_text(self) -> Text:
        return " ".join(self._messages)

    def get_messages(self) -> list:
        return list(self._messages)


class VoiceHandler(InputChannel, ChannelHandlerBase):

    def __init__(self, bot: Text, user: User, request: Request, provider: Text):
        self.bot = bot
        self.user = user
        self.request = request
        self.provider = provider

    @classmethod
    def name(cls) -> Text:
        return ChannelTypes.VOICE.value

    async def validate(self):
        return {"status": "ok"}

    async def handle_message(self):
        raise NotImplementedError("Use handle_incoming_call or handle_call_status")

    def _load_provider(self):
        config = ChatDataProcessor.get_channel_config(
            ChannelTypes.VOICE.value, self.bot, mask_characters=False
        )["config"]
        return VoiceProviderFactory.get_provider(self.provider)(self.bot, config), config

    async def handle_incoming_call(self) -> Text:
        provider_impl, config = self._load_provider()
        form = dict(await self.request.form())
        if not provider_impl.validate_signature(self.request, config["call_url"], form):
            logger.warning("Invalid %s signature on /call — bot=%s provider=%s", self.provider, self.bot, self.provider)
            raise HTTPException(status_code=403, detail=f"Invalid {self.provider} signature")

        call_status = form.get("CallStatus", "")
        speech_result = form.get("SpeechResult", "")
        sender_id = form.get("CallSid", "anonymous")

        if call_status == "ringing" and not speech_result:
            text = config.get("welcomeMessage", "Hello! How can I help you?")
        elif speech_result:
            text = speech_result
        else:
            text = None

        out_channel = VoiceOutput()
        if text is not None:
            metadata = {
                "is_integration_user": True,
                "bot": self.bot,
                "account": self.user.account,
                "channel_type": ChannelTypes.VOICE.value,
                "tabname": "default",
            }
            user_msg = UserMessage(
                text=text,
                output_channel=out_channel,
                sender_id=sender_id,
                input_channel=self.name(),
                metadata=metadata,
            )
            await AgentProcessor.handle_channel_message(self.bot, user_msg)
            messages = out_channel.get_messages()
        else:
            messages = await self._get_reprompt(sender_id, config)

        return provider_impl.build_voice_response(messages, config["call_url"])

    async def _get_reprompt(self, sender_id: Text, config: dict) -> List[str]:
        from rasa.shared.core.events import BotUttered
        fallback = config.get("reprompt_fallback_phrase",
                              "I'm sorry, I didn't get that. Could you please repeat?")
        try:
            agent = AgentProcessor.get_agent(self.bot)
            tracker = await agent.tracker_store.retrieve(sender_id)
            if tracker:
                last = next((e for e in reversed(tracker.events)
                             if isinstance(e, BotUttered)), None)
                if last and last.text:
                    return [last.text]
        except Exception:
            pass
        return [fallback]

    async def handle_call_status(self) -> None:
        provider_impl, config = self._load_provider()
        form = dict(await self.request.form())
        if not provider_impl.validate_signature(self.request, config["status_url"], form):
            logger.warning("Invalid %s signature on /status — bot=%s provider=%s", self.provider, self.bot, self.provider)
            raise HTTPException(status_code=403, detail=f"Invalid {self.provider} signature")
        await provider_impl.handle_call_status(self.request, self.bot)
