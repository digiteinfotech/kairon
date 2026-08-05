from kairon.shared.constants import VoiceProviderTypes
from kairon.shared.voice.exotel.outbound import ExotelOutboundClient
from kairon.shared.voice.twilio import TwilioOutboundClient


class VoiceOutboundFactory:
    __clients = {
        VoiceProviderTypes.twilio.value: TwilioOutboundClient,
        VoiceProviderTypes.exotel.value: ExotelOutboundClient,
    }

    @classmethod
    def get_client(cls, provider: str):
        if provider not in cls.__clients:
            raise ValueError(f"Unsupported voice provider: {provider}")
        return cls.__clients[provider]
