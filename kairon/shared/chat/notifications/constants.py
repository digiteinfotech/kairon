from enum import Enum


class MessageBroadcastLogType(str, Enum):
    common = "common"
    send = "send"
    self = "self"
    script_variables = "script_variables"
