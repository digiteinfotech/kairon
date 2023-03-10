from pydantic import BaseModel, root_validator

from kairon.exceptions import AppException
from kairon.shared.utils import Utility


class ChannelRequest(BaseModel):
    connector_type: str
    config: dict

    @root_validator
    def validate_channel(cls, values):
        if values.get("connector_type") not in Utility.get_channels():
            raise ValueError(f"Invalid channel type {values.get('connector_type')}")
        Utility.validate_channel_config(values['connector_type'], values['config'], ValueError, encrypt=False)
        if values['connector_type'] == "slack":
            if values['config'].get('is_primary') is None:
                values['config']['is_primary'] = True
            if not values['config'].get('is_primary'):
                raise AppException(
                    "Cannot edit secondary slack app. Please delete and install the app again using oAuth."
                )
        return values
