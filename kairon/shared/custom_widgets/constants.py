from enum import Enum


class CustomWidgetParameterType(str, Enum):
    value = "value"
    key_vault = "key_vault"
