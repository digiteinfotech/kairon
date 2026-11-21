from datetime import datetime

import pytz
from croniter import croniter
from pydantic import field_validator, model_validator
from kairon.shared.pydantic_compat import KaironModel

from kairon.shared.chat.broadcast.constants import MessageBroadcastType
from kairon.shared.utils import Utility

from typing import Optional, List, Text, Dict, Any
from kairon.exceptions import AppException



def _apply_root_values(model, values):
    """Apply a v1 root-validator dict onto a model without revalidating.

    Validators may replace a field with another type or drop a key.
    """
    fields = type(model).model_fields
    for name, value in values.items():
        if name in fields and getattr(model, name) is not value:
            setattr(model, name, value)
    for name in fields:
        if name not in values and getattr(model, name) is not None:
            setattr(model, name, None)
    return model


class ChannelRequest(KaironModel):
    connector_type: str
    config: dict

    @model_validator(mode="after")
    def validate_channel(self):
        values = {
            field: getattr(self, field)
            for field in type(self).model_fields
        }
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
        return _apply_root_values(self, values)

class SchedulerConfiguration(KaironModel):
    expression_type: str
    schedule: Any
    timezone: Optional[str] = None

    @model_validator(mode="after")
    def validate_schedule(self):
        values = {
            field: getattr(self, field)
            for field in type(self).model_fields
        }
        expression_type = values.get("expression_type")
        schedule = values.get("schedule")
        tz = values.get("timezone")

        if not expression_type or expression_type not in ["cron", "epoch"]:
            raise ValueError("expression_type must be either cron or epoch")

        if not tz or not tz.strip():
            raise ValueError("timezone is required for all schedules!")

        if schedule is None or (isinstance(schedule, str) and not schedule.strip()):
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

        return _apply_root_values(self, values)


class RecipientsConfiguration(KaironModel):
    recipients: str


class TemplateConfiguration(KaironModel):
    template_id: str
    language: str = "en"
    data: Optional[str] = None


class BroadcastCollectionDataFilter(KaironModel):
    column: str
    condition: str
    value: Any


class CollectionConfig(KaironModel):
    collection: str
    number_field: str
    filters_list: List[BroadcastCollectionDataFilter] = []
    field_mapping: dict


class MessageBroadcastRequest(KaironModel):
    name: str
    connector_type: str
    broadcast_type: MessageBroadcastType
    scheduler_config: Optional[SchedulerConfiguration] = None
    recipients_config: Optional[RecipientsConfiguration] = None
    template_config: Optional[List[TemplateConfiguration]] = None
    collection_config: Optional[CollectionConfig] = None
    template_name: Optional[str] = None
    language_code: Optional[str] = None
    pyscript: Optional[str] = None
    flowname: Optional[str] = None

    @model_validator(mode="after")
    def validate_request(self):
        values = {
            field: getattr(self, field)
            for field in type(self).model_fields
        }
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

        return _apply_root_values(self, values)


class ChatRequest(KaironModel):
    data: Text
    metadata: Optional[Dict] = None

    @field_validator("data")
    @classmethod
    def validate_data(cls, v):
        if Utility.check_empty_string(v):
            raise ValueError("data cannot be empty!")
        return v

class AgenticFlowRequest(KaironModel):
    name: str
    slot_vals: Optional[Dict[str, Any]] = None
    sender_id: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if Utility.check_empty_string(v):
            raise ValueError("name cannot be empty!")
        return v

