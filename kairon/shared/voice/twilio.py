from kairon.shared.voice.base import VoiceOutboundBase


class TwilioOutboundClient(VoiceOutboundBase):
    def initiate_call(self, to_phone: str, twiml_url: str, status_callback_url: str = None) -> str:
        from twilio.rest import Client
        client = Client(self.account_sid, self.auth_token)
        call = client.calls.create(
            to=to_phone,
            from_=self.from_number,
            url=twiml_url,
            status_callback=status_callback_url,
            status_callback_method="POST",
        )
        return call.sid
