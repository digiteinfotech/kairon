"""
Exotel Voice Streaming WebSocket handler.

Bridges an Exotel bidirectional media WebSocket to the provider-agnostic
:class:`~kairon.shared.voice.exotel.session.ExotelCallSession`:

  * authenticates the channel token (same JWT/scope check as the HTTP voice
    webhooks) and loads the bot's voice channel config,
  * builds the configured STT and TTS adapters (credentials from the global
    ``voice.providers`` block of system.yaml; per-bot BYO credentials are layered
    on in the resilience phase),
  * wires an agent runner that drives kairon's agent brain via
    ``AgentProcessor.handle_channel_message`` and collects the reply through the
    existing :class:`~kairon.chat.handlers.channels.voice.VoiceOutput` channel,
  * pumps inbound frames into the session until the caller/socket disconnects.
"""
import json
import logging
from typing import Optional

from fastapi.security import SecurityScopes
from starlette.websockets import WebSocket, WebSocketDisconnect

from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.handlers.channels.voice import VoiceOutput
from kairon.shared.auth import Authentication
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import CHAT_ACCESS, ChannelTypes
from kairon.shared.utils import Utility
from kairon.shared.voice.exotel.session import AgentTurn, ExotelCallSession
from kairon.shared.voice.stt.factory import STTFactory
from kairon.shared.voice.tts.factory import TTSFactory

logger = logging.getLogger(__name__)


class ExotelStreamHandler:
    INPUT_CHANNEL = ChannelTypes.VOICE.value

    def __init__(self, bot: str, provider: str, token: str, websocket: WebSocket):
        self.bot = bot
        self.provider = provider
        self.token = token
        self.websocket = websocket
        self.user = None

    async def authenticate(self) -> bool:
        """Validate the channel token; on failure close the socket and return False."""
        try:
            scopes = SecurityScopes(scopes=CHAT_ACCESS)
            self.user = await Authentication.get_current_user_and_bot(
                scopes, self.websocket, self.token
            )
            return True
        except Exception as e:
            logger.warning("Exotel stream auth failed bot=%s: %s", self.bot, e)
            try:
                await self.websocket.close(code=1008)
            except Exception:
                pass
            return False

    def _voice_env(self) -> dict:
        return Utility.environment.get("voice", {}) or {}

    def _provider_credentials(self, provider: str) -> dict:
        """Global STT/TTS provider credentials from system.yaml (``voice.providers``).
        Per-bot BYO credentials override these in the resilience phase."""
        providers = self._voice_env().get("providers", {}) or {}
        return dict(providers.get(provider, {}) or {})

    def _build_stt(self, config: dict):
        voice_env = self._voice_env()
        provider = (
            config.get("stt_provider")
            or voice_env.get("stt", {}).get("default_provider")
            or "sarvam"
        )
        sample_rate = int(config.get("sample_rate") or voice_env.get("default_sample_rate") or 8000)
        language = config.get("language", "en-IN")
        creds = self._provider_credentials(provider)
        # carry the sample-rate model choice from metadata if present
        metadata = STTFactory.provider_metadata(provider)
        model = (metadata.get("models") or {}).get(str(sample_rate))
        if model and "model" not in creds:
            creds = {**creds, "model": model}
        impl = STTFactory.get(provider)
        return impl(creds, language, sample_rate), provider

    def _build_tts(self, config: dict):
        voice_env = self._voice_env()
        provider = (
            config.get("tts_provider")
            or voice_env.get("tts", {}).get("default_provider")
            or "polly"
        )
        sample_rate = int(config.get("sample_rate") or voice_env.get("default_sample_rate") or 8000)
        language = config.get("language", "en-IN")
        creds = self._provider_credentials(provider)
        metadata = TTSFactory.provider_metadata(provider)
        voice = (
            config.get("voice")
            or (metadata.get("voices") or {}).get(language)
            or metadata.get("default_voice")
        )
        merged = {**creds, "engine": metadata.get("engine", creds.get("engine", "neural"))}
        impl = TTSFactory.get(provider)
        return impl(merged, voice=voice, language=language, sample_rate=sample_rate), provider

    def _base_metadata(self) -> dict:
        return {
            "is_integration_user": True,
            "bot": self.bot,
            "account": getattr(self.user, "account", None),
            "channel_type": ChannelTypes.VOICE.value,
            "tabname": "default",
        }

    def _make_agent_runner(self):
        async def runner(text: str, sender_id: str, metadata: dict) -> AgentTurn:
            from rasa.core.channels.channel import UserMessage

            out_channel = VoiceOutput()
            user_msg = UserMessage(
                text=text,
                output_channel=out_channel,
                sender_id=sender_id,
                input_channel=self.INPUT_CHANNEL,
                metadata=metadata,
            )
            await AgentProcessor.handle_channel_message(self.bot, user_msg)
            return AgentTurn(
                messages=out_channel.get_messages(),
                hangup=out_channel.should_hangup(),
            )

        return runner

    async def run(self) -> None:
        if not await self.authenticate():
            return
        try:
            config = ChatDataProcessor.get_channel_config(
                ChannelTypes.VOICE.value, self.bot, mask_characters=False
            )["config"]
        except Exception as e:
            logger.warning("No voice channel config bot=%s: %s", self.bot, e)
            await self.websocket.close(code=1011)
            return

        voice_env = self._voice_env()
        chunk = voice_env.get("chunk", {}) or {}
        sample_rate = int(config.get("sample_rate") or voice_env.get("default_sample_rate") or 8000)

        try:
            stt, stt_provider = self._build_stt(config)
            tts, tts_provider = self._build_tts(config)
        except Exception as e:
            logger.exception("Failed to build STT/TTS bot=%s: %s", self.bot, e)
            await self.websocket.close(code=1011)
            return

        await self.websocket.accept()

        async def sender(frame: dict) -> None:
            await self.websocket.send_text(json.dumps(frame))

        session = ExotelCallSession(
            bot=self.bot,
            config=config,
            sender=sender,
            stt=stt,
            tts=tts,
            agent_runner=self._make_agent_runner(),
            metadata=self._base_metadata(),
            welcome_message=config.get("welcome_message"),
            chunk_multiple=int(chunk.get("multiple", 320)),
            chunk_max_bytes=int(chunk.get("max_bytes", 100000)),
            sample_rate=sample_rate,
        )
        logger.info(
            "Exotel stream connected bot=%s stt=%s tts=%s", self.bot, stt_provider, tts_provider
        )
        try:
            await session.start()
            while True:
                message = await self.websocket.receive_text()
                await session.on_message(message)
        except WebSocketDisconnect:
            logger.info("Exotel websocket disconnected bot=%s", self.bot)
        except Exception as e:  # pragma: no cover - runtime/network dependent
            logger.exception("Exotel stream error bot=%s: %s", self.bot, e)
        finally:
            await session.close()
