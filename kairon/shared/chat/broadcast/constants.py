from enum import Enum


class MessageBroadcastLogType(str, Enum):
    common = "common"
    send = "send"
    resend = "resend"
    self = "self"
    script_variables = "script_variables"


class MessageBroadcastType(str, Enum):
    static = "static"
    dynamic = "dynamic"


class MetaErrorCodes(str, Enum):
    message_undeliverable = 131026
    recipient_sender_same = 131021
    payment_error = 131042

