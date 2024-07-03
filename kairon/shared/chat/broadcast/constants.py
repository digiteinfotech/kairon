from enum import Enum


class MessageBroadcastLogType(str, Enum):
    common = "common"
    send = "send"
    self = "self"
    script_variables = "script_variables"


class MessageBroadcastType(str, Enum):
    static = "static"
    dynamic = "dynamic"

