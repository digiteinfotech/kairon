import logging
from typing import Text

import requests

from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = 13.0


class WhatsappOnPremise(WhatsappCloud):

    def __init__(self, access_token, **kwargs):
        """
            @required:
                access_token
            @optional:
                session
                api_version
                app_secret
        """
        super().__init__(access_token, **kwargs)
        self.access_token = access_token
        self.session = kwargs.get('session', requests.Session())

    def send_action(self, payload, timeout=None, **kwargs):
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = self.session.post(
            '{app}/messages'.format(app=self.app),
            headers=self.auth_args,
            json=payload,
            timeout=timeout
        )
        resp = r.json()
        logger.debug(resp)
        return resp

    def get_attachment(self, media_id, timeout=None):
        """
            @required:
                media_id: audio/video/image/document id
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = self.session.get(
            '{app}/media/{media_id}'.format(app=self.app, media_id=media_id),
            headers=self.auth_args,
            timeout=timeout
        )
        resp = r.json()
        logger.debug(resp)
        return resp

    def mark_as_read(self, msg_id, timeout=None):
        payload = {
            "status": "read"
        }
        r = self.session.put(
            '{app}/messages/{message_id}'.format(app=self.app, message_id=msg_id),
            headers=self.auth_args,
            json=payload,
            timeout=timeout
        )
        resp = r.json()
        logger.debug(resp)
        return resp

    def send_template_message(self, namespace: Text, name: Text, to_phone_number, language_code: Text = "en"):
        payload = {
            "namespace": namespace,
            "language": {
                "policy": "deterministic",
                "code": language_code
            },
            "name": name
        }
        self.send(payload, to_phone_number, messaging_type="template")
