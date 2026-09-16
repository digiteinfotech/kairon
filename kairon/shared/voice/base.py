from abc import ABC, abstractmethod


class VoiceOutboundBase(ABC):
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        """
        Store outbound call credentials and caller number.

        :param account_sid: telephony provider account SID
        :param auth_token: telephony provider auth token
        :param from_number: caller phone number in E.164 format
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    @abstractmethod
    def initiate_call(self, to_phone: str, twiml_url: str, status_callback_url: str = None) -> str:
        raise NotImplementedError
