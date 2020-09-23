from enum import Enum


class ParameterType(str, Enum):
    user = "user"
    action = "action"
    form = "form"
    slot = "slot"
    http = "http"
    http_action_config = "http_action_config"
