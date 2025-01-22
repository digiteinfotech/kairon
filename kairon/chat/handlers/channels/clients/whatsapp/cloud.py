import hashlib
import hmac
import logging
from typing import Text, Dict
from urllib.parse import urlencode

import requests
from aiohttp import ClientResponseError, ClientConnectionError, ClientError
from aiohttp_retry import ExponentialRetry, RetryClient

from kairon import Utility
from kairon.exceptions import AppException

logger = logging.getLogger(__name__)


DEFAULT_API_VERSION = 19.0
INVALID_STATUS_CODES = set(range(400, 600))


class WhatsappCloud(object):

    # https://developers.facebook.com/docs/whatsapp/cloud-api/guides
    MESSAGING_TYPES = {
        'text',
        'image',
        'video',
        'audio',
        'location',
        'contacts',
        'interactive',
        'template'
    }

    WHATSAPP_REQUEST_TIMEOUT = 120.0  # seconds

    def __init__(self, access_token, **kwargs):
        """
            @required:
                access_token
            @optional:
                session
                api_version
                app_secret
        """

        self.access_token = access_token
        self.from_phone_number_id = kwargs.get('from_phone_number_id')
        if self.client_type == "meta" and Utility.check_empty_string(self.from_phone_number_id):
            raise AppException("missing parameter 'from_phone_number_id'")
        self.session = kwargs.get('session', requests.Session())
        self.api_version = kwargs.get('api_version', DEFAULT_API_VERSION)
        self.app = 'https://graph.facebook.com/v{api_version}'.format(api_version=self.api_version)
        self.app_secret = kwargs.get('app_secret')
        self.metadata = kwargs.get("metadata")

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

    async def send_async(self, payload: dict, to_phone_number: str, messaging_type: str,
                         recipient_type: str = 'individual',
                         timeout: float = WHATSAPP_REQUEST_TIMEOUT, tag=None) -> (bool, int, any):
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

        return await self.send_action_async(body, timeout=timeout)

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
            '{app}/{from_phone_number_id}/messages'.format(app=self.app, from_phone_number_id=self.from_phone_number_id),
            params=self.auth_args,
            json=payload,
            timeout=timeout
        )
        resp = r.json()
        logger.debug(resp)
        return resp

    def get_attachment(self, attachment_id, timeout=None):
        """
            @required:
                attachment_id: audio/video/image/document id
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = self.session.get(
            '{app}/{attachment_id}'.format(app=self.app, attachment_id=attachment_id),
            params=self.auth_args,
            timeout=timeout
        )
        resp = r.json()
        logger.debug(resp)
        return resp

    def mark_as_read(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id}
        return self.send_action(payload)

    def generate_appsecret_proof(self):
        """
            @outputs:
                appsecret_proof: HMAC-SHA256 hash of page access token
                    using app_secret as the key
        """
        app_secret = str(self.app_secret).encode('utf8')
        access_token = str(self.access_token).encode('utf8')

        return hmac.new(app_secret, access_token, hashlib.sha256).hexdigest()

    def send_template_message(self, name: Text, to_phone_number, language_code: Text = "en", components: Dict = None, namespace: Text = None):
        payload = {
            "language": {
                "code": language_code
            },
            "name": name
        }
        if components:
            payload.update({"components": components})
        return self.send(payload, to_phone_number, messaging_type="template")

    async def send_template_message_async(self, name: str, to_phone_number: str, language_code: str = "en",
                                          components: dict = None, namespace: str = None) -> (bool, int, any):
        payload = {
            "language": {
                "code": language_code
            },
            "name": name
        }
        if components:
            payload.update({"components": components})
        return await self.send_async(payload, to_phone_number, messaging_type="template")

    async def send_action_async(self, payload: dict, timeout: float = WHATSAPP_REQUEST_TIMEOUT, attempts: int = 3,
                                **kwargs) -> (bool, int, dict):
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout in seconds
                attempts: number of retry attempts if not succeeded
            @outputs:
                success: True if request is successful, False otherwise
                status_code: response status code
                response: response json
        """
        last_status_code = 500
        last_response = None
        try:
            retry_options = ExponentialRetry(attempts=attempts, statuses=INVALID_STATUS_CODES, max_timeout=timeout)
            url = f'{self.app}/{self.from_phone_number_id}/messages?{urlencode(self.auth_args)}'

            async with RetryClient(raise_for_status=False, retry_options=retry_options) as client:
                async with client.post(url, json=payload) as response:
                    last_status_code = response.status
                    if response.status == 200:
                        resp = await response.json()
                        return True, response.status, resp
                    else:
                        try:
                            last_response = response.json()
                        except Exception as e:
                            last_response = response.text

                return False, last_status_code, last_response
        except ClientResponseError as cre:
            return False, last_status_code, {"error": str(cre), "response": last_response}
        except ClientConnectionError as cce:
            return False, last_status_code, {"error": str(cce), "response": last_response}
        except ClientError as ce:
            return False, last_status_code, {"error": str(ce), "response": last_response}
        except Exception as e:
            return False, last_status_code, {"error": str(e), "response": last_response}