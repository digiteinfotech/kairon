from typing import Type

from kairon.exceptions import AppException
from kairon.chat.handlers.channels.clients.voice.base import VoiceProviderBase
from kairon.shared.constants import VoiceProviderTypes


class VoiceProviderFactory:

    __implementations = {}

    @classmethod
    def _get_implementations(cls) -> dict:
        if not cls.__implementations:
            from kairon.chat.handlers.channels.clients.voice.twilio import TwilioVoiceProvider
            cls.__implementations = {
                VoiceProviderTypes.twilio.value: TwilioVoiceProvider,
            }
        return cls.__implementations

    @classmethod
    def get_provider(cls, provider: str) -> Type[VoiceProviderBase]:
        impls = cls._get_implementations()
        if provider not in impls:
            raise AppException(f"Voice provider '{provider}' not implemented")
        return impls[provider]
