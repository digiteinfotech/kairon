from enum import Enum


class SLACKCONSTANT(str, Enum):
    slack_connector = "slack"
    slack_channel = "slack_channel"
    slack_token = "slack_token"
    slack_signing_secret = "slack_signing_secret"