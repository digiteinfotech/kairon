from enum import Enum


class MessageBroadcastLogType(str, Enum):
    common = "common"
    send = "send"
    resend = "resend"
    self = "self"
    script_variables = "script_variables"
    progress = "progress"


class MessageBroadcastType(str, Enum):
    static = "static"
    dynamic = "dynamic"
    flow = "flow"

