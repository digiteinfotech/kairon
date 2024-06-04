from enum import Enum


class BotSecretType(str, Enum):
    gpt_key = "gpt_key"
    d360_api_key = "d360_api_key"
