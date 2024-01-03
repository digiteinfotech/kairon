import hashlib
import hmac
import logging
from typing import Text, Dict

from kairon import Utility
from kairon.exceptions import AppException

logger = logging.getLogger(__name__)


DEFAULT_API_VERSION = 13.0


class WhatsappCloud(object):

    # https://developers.facebook.com/docs/whatsapp/cloud-api/guides
    MESSAGING_TYPES = {
        'text',
        'image',
        'location',
        'contacts',
        'interactive',
        'template'
    }

    def __init__(self, access_token, session, **kwargs):
        """
            @required:
                access_token
            @optional:
                client
                api_version
                app_secret
        """

        self.access_token = access_token
        self.session = session
        self.from_phone_number_id = kwargs.get('from_phone_number_id')
        if self.client_type == "meta" and Utility.check_empty_string(self.from_phone_number_id):
            raise AppException("missing parameter 'from_phone_number_id'")
        self.api_version = kwargs.get('api_version', DEFAULT_API_VERSION)
        self.app = 'https://graph.facebook.com/v{api_version}'.format(api_version=self.api_version)
        self.app_secret = kwargs.get('app_secret')

    @property
    def client_type(self):
        return "meta"

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

    async def send(self, payload, to_phone_number, messaging_type, recipient_type='individual', timeout=None, tag=None):
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

        response = await self.send_action(body)
        return response

    async def send_json(self, payload: dict, to_phone_number, recipient_type='individual', timeout=None):
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

        response = await self.send_action(payload)
        return response

    async def send_action(self, payload, timeout=None, **kwargs):
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        url = '{app}/{from_phone_number_id}/messages'.format(app=self.app,
                                                                 from_phone_number_id=self.from_phone_number_id)
        response = await self.session.request("POST", url, headers=self.auth_args, request_body=payload, timeout=timeout,
                                              return_json=False)
        resp = await response.text()
        logger.debug(resp)
        return resp

    async def get_attachment(self, attachment_id, timeout=None):
        """
            @required:
                attachment_id: audio/video/image/document id
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        url = '{app}/{attachment_id}'.format(app=self.app, attachment_id=attachment_id)
        response = await self.session.request("GET", url, headers=self.auth_args, timeout=timeout,
                                              return_json=False)
        resp = await response.text()
        logger.debug(resp)
        return resp

    async def mark_as_read(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id}
        response = await self.send_action(payload)
        return response

    def generate_appsecret_proof(self):
        """
            @outputs:
                appsecret_proof: HMAC-SHA256 hash of page access token
                    using app_secret as the key
        """
        app_secret = str(self.app_secret).encode('utf8')
        access_token = str(self.access_token).encode('utf8')

        return hmac.new(app_secret, access_token, hashlib.sha256).hexdigest()

    async def send_template_message(self, name: Text, to_phone_number, language_code: Text = "en", components: Dict = None, namespace: Text = None):
        payload = {
            "language": {
                "code": language_code
            },
            "name": name
        }
        if components:
            payload.update({"components": components})
        response = await self.send(payload, to_phone_number, messaging_type="template")
        return response
