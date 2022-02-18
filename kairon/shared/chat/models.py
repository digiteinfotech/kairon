from pydantic import BaseModel, validator
from kairon.shared.utils import Utility


class ChannelRequest(BaseModel):
    connector_type: str
    config: dict

    @validator("connector_type")
    def validate_connector_type(cls, v, values, **kwargs):
        if v not in Utility.get_channels():
            raise ValueError(
                f"Invalid channel type {v}")
        return v

    @validator("config")
    def validate_channel_config_model(cls, v, values, **kwargs):
        if 'connector_type' in values:
            Utility.validate_channel_config(values['connector_type'], v, ValueError, encrypt=False)
        return v
