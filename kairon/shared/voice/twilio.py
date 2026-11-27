from kairon.shared.voice.base import VoiceOutboundBase


class TwilioOutboundClient(VoiceOutboundBase):
    def place_call(self, to_phone: str, channel_config: dict) -> str:
        """Dial ``to_phone`` and answer it with the channel's ``call_url``."""
        return self.initiate_call(to_phone, channel_config.get("call_url", ""), channel_config.get("status_url", ""))

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
