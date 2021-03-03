from abc import ABC
from typing import Any

from kairon.chat_server.channels.channels import KaironChannels
from kairon.chat_server.exceptions import ChatServerException


class ChatServerResponse:

    def __init__(self, message: str, data: Any = None, success: bool = True):
        self.message = message
        self.success = success
        self.data = data

    def get_json(self):
        return {
            "message": self.message,
            "data": self.data,
            "success": self.success
        }


class ChatServerRequestInterface(ABC):

    def validate(self):
        raise NotImplementedError


class CreateClientRequest(ChatServerRequestInterface):

    def __init__(self, channel, credentials):
        self.channel = channel
        self.credentials = credentials

    def validate(self):
        if self.channel not in [KaironChannels.TELEGRAM]:
            raise ChatServerException("Channel not supported!")

        if not isinstance(self.credentials, dict):
            raise ChatServerException("Invalid request body!")


class GetClientRequest(ChatServerRequestInterface):

    def __init__(self, channel):
        self.channel = channel

    def validate(self):
        if self.channel not in [KaironChannels.TELEGRAM]:
            raise ChatServerException("Channel not supported!")


class ChatRequest(ChatServerRequestInterface):

    def __init__(self, text):
        self.text = text

    def validate(self):
        pass
