from enum import Enum

KAIRON_ACTION_RESPONSE_SLOT = "KAIRON_ACTION_RESPONSE"


class ParameterType(str, Enum):
    user = "user"
    action = "action"
    form = "form"
    slot = "slot"
    http = "http"
    sender_id = "sender_id"
    http_action_config = "http_action_config"


class ActionType(str, Enum):
    http_action = "http_action"
    slot_set_action = "slot_set_action"
