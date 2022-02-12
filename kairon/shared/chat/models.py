from pydantic import BaseModel, validator
from kairon.shared.chat.constant import SLACKCONSTANT


class ChannelsRequest(BaseModel):
    connector_type: str
    config: dict

    @validator("config", allow_reuse=True)
    def validate_channel_config(cls, v, values, **kwargs):
        if 'connector_type' in values and values['connector_type'] == SLACKCONSTANT.slack_connector.value:
            if (SLACKCONSTANT.slack_token.value not in v
                    or SLACKCONSTANT.slack_signing_secret.value not in v):
                raise ValueError(
                    f"Missing {SLACKCONSTANT.slack_token.value} or {SLACKCONSTANT.slack_signing_secret.value} in config")
        return v

    @validator("connector_type", allow_reuse=True)
    def validate_channel_type(cls, v, values, **kwargs):
        if v not in [SLACKCONSTANT.slack_connector.value]:
            raise ValueError(
                f"Invalid channel type {v}")
        return v
