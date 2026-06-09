from kairon.shared.voice.twilio import TwilioOutboundClient


class VoiceOutboundFactory:
    __clients = {
        "twilio": TwilioOutboundClient,
    }

    @classmethod
    def get_client(cls, provider: str):
        if provider not in cls.__clients:
            raise ValueError(f"Unsupported voice provider: {provider}")
        return cls.__clients[provider]
