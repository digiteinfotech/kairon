from datetime import datetime

import pytz
from croniter import croniter
from pydantic import BaseModel, root_validator, validator

from kairon.shared.chat.broadcast.constants import MessageBroadcastType
from kairon.shared.utils import Utility

from typing import List, Text, Dict, Any
from kairon.exceptions import AppException


class ChannelRequest(BaseModel):
    connector_type: str
    config: dict

    @root_validator
    def validate_channel(cls, values):
        if values.get("connector_type") not in Utility.get_channels():
            raise ValueError(f"Invalid channel type {values.get('connector_type')}")
        Utility.validate_channel_config(
            values["connector_type"], values["config"], ValueError, encrypt=False
        )
        if values["connector_type"] == "slack":
            if values["config"].get("is_primary") is None:
                values["config"]["is_primary"] = True
            if not values["config"].get("is_primary"):
                raise AppException(
                    "Cannot edit secondary slack app. Please delete and install the app again using oAuth."
                )
        return values

class SchedulerConfiguration(BaseModel):
    expression_type: str
    schedule: str
    timezone: str = None

    @root_validator
    def validate_schedule(cls, values):
        expression_type = values.get("expression_type")
        schedule = values.get("schedule")
        tz = values.get("timezone")

        if not expression_type or expression_type not in ["cron", "epoch"]:
            raise ValueError("expression_type must be either cron or epoch")

        if not tz or not tz.strip():
            raise ValueError("timezone is required for all schedules!")

        if not schedule or not schedule.strip():
            raise ValueError("schedule time is required for all schedules!")

        if expression_type == "cron":
            if not croniter.is_valid(schedule):
                raise ValueError(f"Invalid cron expression: '{schedule}'")

            first_occurrence = croniter(schedule).get_next(ret_type=datetime)
            second_occurrence = croniter(schedule).get_next(ret_type=datetime, start_time=first_occurrence)

            min_trigger_interval = Utility.environment["events"]["scheduler"]["min_trigger_interval"]
            if (second_occurrence - first_occurrence).total_seconds() < min_trigger_interval:
                raise ValueError(
                    f"Recurrence interval must be at least {min_trigger_interval} seconds!"
                )

        elif expression_type == "epoch":
            try:
                epoch_time = int(schedule)
            except ValueError:
                raise ValueError("schedule must be a valid integer epoch time for 'epoch' expression_type")

            try:
                user_tz = pytz.timezone(tz)
            except pytz.UnknownTimeZoneError:
                raise ValueError(f"Unknown timezone: {tz}")

            current_epoch_in_tz = int(datetime.now(user_tz).timestamp())

            if epoch_time <= current_epoch_in_tz:
                raise ValueError("epoch time (schedule) must be in the future relative to the provided timezone")

            values["schedule"] = epoch_time

        return values


class RecipientsConfiguration(BaseModel):
    recipients: str


class TemplateConfiguration(BaseModel):
    template_id: str
    language: str = "en"
    data: str = None


class BroadcastCollectionDataFilter(BaseModel):
    column: str
    condition: str
    value: Any


class CollectionConfig(BaseModel):
    collection: str
    number_field: str
    filters_list: List[BroadcastCollectionDataFilter] = []
    field_mapping: dict


class MessageBroadcastRequest(BaseModel):
    name: str
    connector_type: str
    broadcast_type: MessageBroadcastType
    scheduler_config: SchedulerConfiguration = None
    recipients_config: RecipientsConfiguration = None
    template_config: List[TemplateConfiguration] = None
    collection_config: CollectionConfig = None
    template_name: str = None
    language_code: str = None
    pyscript: str = None
    flowname: str = None

    @root_validator
    def validate_request(cls, values):
        if values.get("broadcast_type") == MessageBroadcastType.static:
            if not values.get("recipients_config") or not values.get("template_config"):
                raise ValueError(
                    "recipients_config and template_config is required for static broadcasts!"
                )

        if values.get("broadcast_type") == MessageBroadcastType.dynamic:
            if not values.get("template_name"):
                raise ValueError("template_name is required for dynamic broadcasts!")
            if not values.get("language_code"):
                raise ValueError("language_code is required for dynamic broadcasts!")

        pyscript = values.get("pyscript")
        if values.get(
            "broadcast_type"
        ) == MessageBroadcastType.dynamic and Utility.check_empty_string(pyscript):
            raise ValueError("pyscript is required for dynamic broadcasts!")

        return values


class ChatRequest(BaseModel):
    data: Text
    metadata: Dict = None

    @validator("data")
    def validate_data(cls, v, values, **kwargs):
        if Utility.check_empty_string(v):
            raise ValueError("data cannot be empty!")
        return v

class AgenticFlowRequest(BaseModel):
    name: str
    slot_vals: Dict[str, Any] = None
    sender_id: str = None

    @validator("name")
    def validate_name(cls, v, values, **kwargs):
        if Utility.check_empty_string(v):
            raise ValueError("name cannot be empty!")
        return v

