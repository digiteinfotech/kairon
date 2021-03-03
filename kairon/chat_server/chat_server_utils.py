import datetime
import os
from glob import iglob

from jwt import PyJWTError, decode, encode, ExpiredSignatureError, InvalidTokenError
from rasa.utils.endpoints import EndpointConfig
from smart_config import ConfigLoader

from kairon.chat_server.exceptions import AuthenticationException, ChatServerException


class ChatServerUtils:
    environment = {}

    @staticmethod
    def load_evironment():
        """
        Loads the environment variables and their values from the
        chat-config.yaml file for defining the working environment of the app
        :return: None
        """
        ChatServerUtils.environment = ConfigLoader(
            os.getenv("chat-config", "./chat-config.yaml")).get_config()

    @staticmethod
    def encode_auth_token(user):
        """
        Generates the Auth Token
        :return: string
        """
        try:
            expiry_time = ChatServerUtils.environment['security']["token_expire"]
            payload = {
                'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=expiry_time),
                'iat': datetime.datetime.utcnow(),
                'sub': user
            }
            secret_key = ChatServerUtils.environment['security']['secret_key']
            algorithm = ChatServerUtils.environment['security']['algorithm']
            return encode(
                payload,
                secret_key,
                algorithm=algorithm
            )
        except Exception as e:
            raise AuthenticationException(e)

    @staticmethod
    def decode_auth_token(auth_token):
        """
        Decodes the auth token
        :param auth_token:
        :return: integer|string
        """
        try:
            secret_key = ChatServerUtils.environment['security']['secret_key']
            payload = decode(
                auth_token,
                secret_key)
            username = payload['sub']
            if not username:
                raise AuthenticationException("Could not identify the user")
            return username
        except ExpiredSignatureError:
            raise AuthenticationException('Signature expired.')
        except InvalidTokenError:
            raise AuthenticationException('Invalid token.')

    @staticmethod
    def is_empty(value: str):
        """
        checks for empty string

        :param value: string value
        :return: boolean
        """
        if not value:
            return True
        if not value.strip():
            return True
        else:
            return False
