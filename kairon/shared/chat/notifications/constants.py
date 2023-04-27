from enum import Enum


class MessageBroadcastLogType(str, Enum):
    common = "common"
    send = "send"
