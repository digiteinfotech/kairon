import hashlib
import hmac
import logging

import requests

logger = logging.getLogger(__name__)


DEFAULT_API_VERSION = 13.0


class WhatsappClient(object):

    # https://developers.facebook.com/docs/whatsapp/cloud-api/guides
    MESSAGING_TYPES = {
        'text',
        'image',
        'location',
        'contacts',
        'interactive',
        'template'
    }

    def __init__(self, access_token, from_phone_number_id, **kwargs):
        """
            @required:
                access_token
            @optional:
                session
                api_version
                app_secret
        """

        self.access_token = access_token
        self.from_phone_number_id = from_phone_number_id
        self.session = kwargs.get('session', requests.Session())
        self.api_version = kwargs.get('api_version', DEFAULT_API_VERSION)
        self.graph_url = 'https://graph.facebook.com/v{api_version}'.format(api_version=self.api_version)
        self.app_secret = kwargs.get('app_secret')

    @property
    def auth_args(self):
        if not hasattr(self, '_auth_args'):
            auth = {
                'access_token': self.access_token
            }
            if self.app_secret is not None:
                appsecret_proof = self.generate_appsecret_proof()
                auth['appsecret_proof'] = appsecret_proof
            self._auth_args = auth
        return self._auth_args

    def send(self, payload, to_phone_number, messaging_type, recipient_type='individual', timeout=None, tag=None):
        """
            @required:
                payload: message request payload
                to_phone_number: receiver's phone number
                messaging_type: text/document, etc
            @optional:
                recipient_type: recipient type
                timeout: request timeout
                tag
            @outputs: response json
        """
        if messaging_type not in self.MESSAGING_TYPES:
            raise ValueError('`{}` is not a valid `messaging_type`'.format(messaging_type))

        body = {
            'messaging_product': "whatsapp",
            'recipient_type': recipient_type,
            "to": to_phone_number,
            "type": messaging_type,
            messaging_type: payload
        }

        if tag:
            body['tag'] = tag

        return self.send_action(body)

    def send_json(self, payload: dict, to_phone_number, recipient_type='individual', timeout=None):
        """
            @required:
                payload: message request payload
                to_phone_number: receiver's phone number
            @optional:
                recipient_type: recipient type
                timeout: request timeout
            @outputs: response json
        """
        payload.update({
            'messaging_product': "whatsapp",
            'recipient_type': recipient_type,
            "to": to_phone_number
        })

        return self.send_action(payload)

    def send_action(self, payload, timeout=None, **kwargs):
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = self.session.post(
            '{graph_url}/{from_phone_number_id}/messages'.format(
                graph_url=self.graph_url, from_phone_number_id=self.from_phone_number_id
            ),
            params=self.auth_args,
            json=payload,
            timeout=timeout
        )
        return r.json()

    def get_attachment(self, attachment_id, timeout=None):
        """
            @required:
                attachment_id: audio/video/image/document id
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = self.session.get(
            '{graph_url}/{attachment_id}'.format(
                graph_url=self.graph_url, attachment_id=attachment_id
            ),
            params=self.auth_args,
            timeout=timeout
        )
        return r.json()

    def generate_appsecret_proof(self):
        """
            @outputs:
                appsecret_proof: HMAC-SHA256 hash of page access token
                    using app_secret as the key
        """
        app_secret = str(self.app_secret).encode('utf8')
        access_token = str(self.access_token).encode('utf8')

        return hmac.new(app_secret, access_token, hashlib.sha256).hexdigest()
