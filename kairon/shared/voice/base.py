from abc import ABC, abstractmethod


class VoiceOutboundBase(ABC):
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        """Store outbound call credentials and caller number.

        :param account_sid: telephony provider account SID
        :param auth_token: telephony provider auth token
        :param from_number: caller phone number in E.164 format
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    @classmethod
    def from_config(cls, config: dict) -> "VoiceOutboundBase":
        """Build a client from a decrypted voice channel config dict."""
        return cls(
            account_sid=config["account_sid"],
            auth_token=config["auth_token"],
            from_number=config["phone_number"],
        )

    @abstractmethod
    def place_call(self, to_phone: str, channel_config: dict) -> str:
        """Dial ``to_phone`` as the voice channel is configured to; return the provider's call id."""
        raise NotImplementedError

    @abstractmethod
    def initiate_call(self, to_phone: str, twiml_url: str, status_callback_url: str = None) -> str:
        raise NotImplementedError
