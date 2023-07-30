from datetime import datetime

from croniter import croniter
from pydantic import BaseModel, root_validator

from kairon.shared.utils import Utility

from typing import List
import validators
from kairon.exceptions import AppException

ValidationFailure = validators.ValidationFailure


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


class SchedulerConfiguration(BaseModel):
    expression_type: str = "cron"
    schedule: str
    timezone: str = None

    @root_validator
    def validate_config(cls, values):
        if values.get("expression_type") == "cron":
            if not values.get("schedule") or not croniter.is_valid(values.get("schedule")):
                raise ValueError(f"Invalid cron expression: '{values.get('schedule')}'")
            first_occurrence = croniter(values.get("schedule")).get_next(ret_type=datetime)
            second_occurrence = croniter(values.get("schedule")).get_next(ret_type=datetime, start_time=first_occurrence)
            min_trigger_interval = Utility.environment["events"]["scheduler"]["min_trigger_interval"]
            if (second_occurrence - first_occurrence).total_seconds() < min_trigger_interval:
                raise ValueError(f"recurrence interval must be at least {min_trigger_interval} seconds!")
            if Utility.check_empty_string(values.get("timezone")):
                raise ValueError(f"timezone is required for cron expressions!")

        return values


class DataExtractionConfiguration(BaseModel):
    url: str
    headers: dict = None


class RecipientsConfiguration(BaseModel):
    recipient_type: str
    recipients: str


class TemplateConfiguration(BaseModel):
    template_type: str
    template_id: str
    namespace: str
    language: str = "en"
    data: str = None


class MessageBroadcastRequest(BaseModel):
    name: str
    connector_type: str
    scheduler_config: SchedulerConfiguration = None
    data_extraction_config: DataExtractionConfiguration = None
    recipients_config: RecipientsConfiguration = None
    template_config: List[TemplateConfiguration] = None
    pyscript: str = None
