"""Exotel Voice Streaming WebSocket handler.

Bridges an Exotel bidirectional media WebSocket to the provider-agnostic
:class:`~kairon.shared.voice.exotel.session.ExotelCallSession`:

  * authenticates the channel token (same JWT/scope check as the HTTP voice
    webhooks) and loads the bot's voice channel config,
  * builds the configured STT and TTS adapters (credentials resolved from
    ``SpeechProviderConfig`` — bot-scoped entries override global ones),
  * wires an agent runner that drives kairon's agent brain via
    ``AgentProcessor.handle_channel_message`` and collects the reply through the
    existing :class:`~kairon.chat.handlers.channels.voice.VoiceOutput` channel,
  * pumps inbound frames into the session until the caller/socket disconnects.
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from fastapi.security import SecurityScopes
from rasa.shared.core.events import BotUttered, SlotSet
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.handlers.channels.voice import VoiceOutput
from kairon.shared.auth import Authentication
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import CHAT_ACCESS, ChannelTypes
from kairon.shared.utils import Utility
from kairon.shared.voice.cache import TTSCache
from kairon.shared.voice.constants import CallEndReason, DEFAULT_SAMPLE_RATE, DEFAULT_SPEECH_PROVIDER
from kairon.shared.voice.exotel.session import AgentTurn, ExotelCallSession
from kairon.shared.voice.metrics import CallMetrics, persist_call_metrics
from kairon.shared.voice.processor import SpeechProviderConfigProcessor
from kairon.shared.voice.resilience import FallbackSTT, FallbackTTS
from kairon.shared.voice.stt.factory import STTFactory
from kairon.shared.voice.tts.factory import TTSFactory
from kairon.shared.voice.utils import VoiceUtils

logger = logging.getLogger(__name__)

# Process-wide TTS cache shared across calls so repeated prompts (welcome,
# re-prompts, menu options) are synthesised once.
_TTS_CACHE = TTSCache()


@dataclass
class _SpeechSetup:
    """The speech adapters of one call and what is needed to rebuild them for another sample rate."""

    stt: object
    tts: object
    stt_provider: str
    tts_provider: str
    tts_language: str
    tts_voice: Optional[str]
    resolved: dict
    stt_chain: list
    tts_chain: list


class ExotelStreamHandler:
    """Serves one Exotel call over the stream websocket."""

    INPUT_CHANNEL = ChannelTypes.VOICE.value

    def __init__(self, bot: str, provider: str, token: str, websocket: WebSocket):
        """Store bot id, provider name, stream token and WebSocket for this call."""
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
            except Exception as close_err:
                logger.debug("WS close failed: %s", close_err)
            return False

    async def _record_call_messages(
        self, sender_id: str, messages: List[str], slots: Optional[dict], metadata: dict
    ) -> None:
        """Append carried slots and bot-only utterances (welcome, reprompts, goodbye) to the call's tracker.

        The agent stores caller turns and its own replies itself; what the session says without the agent would be
        missing from the history. The first write for a ``sender_id`` starts the bot's session with ``metadata``
        (channel, caller phone, call sid), as the first caller turn would have. It happens under the conversation's
        lock, because a reprompt or goodbye can be recorded while an agent turn is saving its own events.
        """
        processor = AgentProcessor.get_agent(self.bot).processor
        async with processor.lock_store.lock(sender_id):
            tracker = await processor.fetch_tracker_with_initial_session(sender_id, None, metadata)
            if slots:
                known = {slot.name for slot in processor.domain.slots}
                for name, value in slots.items():
                    if name in known:
                        tracker.update(SlotSet(name, value))
                    else:
                        logger.debug(
                            "Skipping carried slot '%s' not defined in the bot domain bot=%s", name, self.bot
                        )
            for message in messages or []:
                if message and message.strip():
                    tracker.update(
                        BotUttered(text=message, metadata={"channel": "voice", "source": "voice_session"})
                    )
            await processor.save_tracker(tracker)

    def _caller_disconnected(self, error: Exception) -> bool:
        """True if ``error`` just means the other side hung up (starlette raises RuntimeError on a dead socket)."""
        if getattr(self.websocket, "client_state", None) == WebSocketState.DISCONNECTED:
            return True
        return isinstance(error, RuntimeError) and "not connected" in str(error).lower()

    def _voice_env(self) -> dict:
        """The ``voice`` section of the system config."""
        return Utility.environment.get("voice", {}) or {}

    def _provider_chain(self, config: dict, service: str, default: str) -> list:
        """Return an ordered, de-duplicated provider list with the bot's choice first.

        The bot's configured provider is placed first, followed by the global
        ``fallback_order``.
        """
        voice_env = self._voice_env()
        chosen = config.get(f"{service}_provider") or voice_env.get(service, {}).get("default_provider")
        order = list(voice_env.get(service, {}).get("fallback_order", []) or [])
        chain = []
        for provider in [chosen, *order, default]:
            if provider and provider not in chain:
                chain.append(provider)
        return chain

    def _stt_builder(self, provider: str, language: str, sample_rate: int, resolved: dict):
        """Factory of the STT adapter for ``provider``; credentials come from its resolved speech config."""
        def build():
            entry = resolved.get(provider) or {}
            creds = {**entry.get("metadata", {}), **entry.get("secrets", {})}
            factory_meta = STTFactory.provider_metadata(provider)
            model = (factory_meta.get("models") or {}).get(str(sample_rate))
            if model and "model" not in creds:
                creds = {**creds, "model": model}
            return STTFactory.get(provider)(creds, language, sample_rate)

        return build

    @staticmethod
    def _spc_voice(entry: dict):
        """Voice for a provider: the common ``voice`` key of its SpeechProviderConfig (bot, else global).

        Each TTS adapter maps it to its provider's own parameter (Sarvam ``speaker``, Polly ``VoiceId``).
        """
        return ((entry or {}).get("metadata") or {}).get("voice")

    def _tts_builder(self, provider: str, language: str, sample_rate: int, resolved: dict):
        """Factory of the TTS adapter for ``provider``; credentials and voice come from its resolved speech config."""
        def build():
            entry = resolved.get(provider) or {}
            creds = {**entry.get("metadata", {}), **entry.get("secrets", {})}
            factory_meta = TTSFactory.provider_metadata(provider)
            merged = {**creds, "engine": factory_meta.get("engine", creds.get("engine", "neural"))}
            return TTSFactory.get(provider)(
                merged, voice=self._spc_voice(entry), language=language, sample_rate=sample_rate
            )

        return build

    def _build_stt(self, config: dict, sample_rate: int, resolved: dict, chain: list):
        """Build the STT with fallback over ``chain``; returns ``(stt, primary_provider)``."""
        language = config.get("language", "en-IN")
        builders = [
            (p, self._stt_builder(p, language, sample_rate, resolved)) for p in chain
        ]
        return FallbackSTT(builders), chain[0]

    def _build_tts(self, config: dict, sample_rate: int, resolved: dict, chain: list):
        """Build the TTS with fallback over ``chain``; returns ``(tts, primary_provider, language, voice)``."""
        language = config.get("language", "en-IN")
        builders = [
            (p, self._tts_builder(p, language, sample_rate, resolved)) for p in chain
        ]
        return FallbackTTS(builders), chain[0], language, self._spc_voice(resolved.get(chain[0]))

    def _base_metadata(self) -> dict:
        """Message metadata every turn of this call carries."""
        return {
            "is_integration_user": True,
            "bot": self.bot,
            "account": getattr(self.user, "account", None),
            "channel_type": ChannelTypes.VOICE.value,
            "tabname": "default",
        }

    def _make_agent_runner(self):
        """The coroutine the session calls with each thing the caller said."""
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

    async def _load_channel_config(self) -> Optional[dict]:
        """The bot's decrypted voice channel config, or None (the socket is closed) if there is none."""
        try:
            return ChatDataProcessor.get_channel_config(
                ChannelTypes.VOICE.value, self.bot, mask_characters=False
            )["config"]
        except Exception as e:
            logger.warning("No voice channel config bot=%s: %s", self.bot, e)
            await self.websocket.close(code=1011)
            return None

    async def _build_speech(self, config: dict, sample_rate: int) -> Optional[_SpeechSetup]:
        """Resolve the speech provider configs and build the STT/TTS; None (the socket is closed) on failure."""
        stt_chain = self._provider_chain(config, "stt", DEFAULT_SPEECH_PROVIDER)
        tts_chain = self._provider_chain(config, "tts", DEFAULT_SPEECH_PROVIDER)
        resolved = SpeechProviderConfigProcessor.resolve(self.bot, list({*stt_chain, *tts_chain}))
        try:
            stt, stt_provider = self._build_stt(config, sample_rate, resolved, stt_chain)
            tts, tts_provider, tts_language, tts_voice = self._build_tts(config, sample_rate, resolved, tts_chain)
        except Exception as e:
            logger.exception("Failed to build STT/TTS bot=%s: %s", self.bot, e)
            await self.websocket.close(code=1011)
            return None
        return _SpeechSetup(stt, tts, stt_provider, tts_provider, tts_language, tts_voice, resolved, stt_chain, tts_chain)

    def _build_session(self, config: dict, speech: _SpeechSetup, sample_rate: int) -> ExotelCallSession:
        """Wire the call session to this websocket, the speech adapters, call tracking and chat history."""
        chunk = self._voice_env().get("chunk", {}) or {}
        loop = asyncio.get_running_loop()

        async def sender(frame: dict) -> None:
            """Send one protocol frame to Exotel."""
            await self.websocket.send_text(json.dumps(frame))

        async def hangup() -> None:
            """Close the websocket; that is what makes Exotel end the call."""
            await self.websocket.close(code=1000)

        async def record(sender_id, messages, slots, metadata) -> None:
            """Write the call's bot messages (and carried-over slots) to the conversation history."""
            await self._record_call_messages(sender_id, messages, slots, metadata)

        async def load_context(call_sid: str) -> dict:
            """Fetch what the outbound call row carried (slots, origin) without blocking the loop."""
            return await loop.run_in_executor(None, VoiceUtils.load_call_context, self.bot, call_sid)

        async def rebuild_audio(rate: int):
            """Build STT/TTS for the sample rate Exotel actually negotiated."""
            new_stt, _ = self._build_stt(config, rate, speech.resolved, speech.stt_chain)
            new_tts, _, new_language, new_voice = self._build_tts(config, rate, speech.resolved, speech.tts_chain)
            return new_stt, new_tts, f"{speech.tts_provider}:{new_voice or ''}:{new_language}:{rate}"

        async def call_ended(call_sid: str, end_reason: str, duration: float) -> None:
            """Record how the call ended on its tracking row."""
            await loop.run_in_executor(None, VoiceUtils.finish_call, self.bot, call_sid, end_reason, duration)

        metrics = CallMetrics(
            bot=self.bot, call_sid="", provider=self.provider,
            stt_provider=speech.stt_provider, tts_provider=speech.tts_provider,
            sink=persist_call_metrics,
        )
        return ExotelCallSession(
            bot=self.bot,
            config=config,
            sender=sender,
            stt=speech.stt,
            tts=speech.tts,
            agent_runner=self._make_agent_runner(),
            metadata=self._base_metadata(),
            welcome_message=config.get("welcome_message"),
            chunk_multiple=int(chunk.get("multiple", 320)),
            chunk_max_bytes=int(chunk.get("max_bytes", 100000)),
            sample_rate=sample_rate,
            metrics=metrics,
            tts_cache=_TTS_CACHE,
            tts_cache_namespace=f"{speech.tts_provider}:{speech.tts_voice or ''}:{speech.tts_language}:{sample_rate}",
            on_hangup=hangup,
            history_recorder=record,
            call_context_loader=load_context,
            on_call_end=call_ended,
            rebuild_audio=rebuild_audio,
        )

    async def _pump(self, session: ExotelCallSession) -> None:
        """Feed inbound websocket frames to the session until the call ends, then close the session."""
        try:
            await session.start()
            while not session.closed:
                message = await self.websocket.receive_text()
                await session.on_message(message)
        except WebSocketDisconnect:
            logger.info("Exotel websocket disconnected bot=%s", self.bot)
        except Exception as e:
            if session.closed or session.ending:
                logger.debug("Exotel websocket closed after hangup bot=%s: %s", self.bot, e)
            elif self._caller_disconnected(e):
                logger.info("Exotel websocket disconnected bot=%s: %s", self.bot, e)
            else:
                session.end_reason = session.end_reason or CallEndReason.ERROR.value
                logger.exception("Exotel stream error bot=%s: %s", self.bot, e)
        finally:
            await session.close()

    async def run(self) -> None:
        """Serve one call: authenticate, build the session and pump frames until the call ends."""
        if not await self.authenticate():
            return
        config = await self._load_channel_config()
        if config is None:
            return
        sample_rate = int(config.get("sample_rate") or self._voice_env().get("default_sample_rate") or DEFAULT_SAMPLE_RATE)
        speech = await self._build_speech(config, sample_rate)
        if speech is None:
            return
        await self.websocket.accept()
        session = self._build_session(config, speech, sample_rate)
        logger.info(
            "Exotel stream connected bot=%s stt=%s tts=%s rate=%s",
            self.bot, speech.stt_provider, speech.tts_provider, sample_rate,
        )
        await self._pump(session)
