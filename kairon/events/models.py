import re
from datetime import datetime
from typing import Any, Dict, Literal, Text

import pytz
from dateutil.parser import isoparse
from pydantic import BaseModel, Extra, StrictStr, ValidationError, validator

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass


class EventRequest(BaseModel):
    data: Dict
    cron_exp: Text = None
    timezone: Text = None
    run_at: Text = None

    class Config:
        use_enum_values = True

    @validator("data")
    def validate_data(cls, v, values, **kwargs):
        if Utility.check_empty_string(v.get("user")) or Utility.check_empty_string(v.get("bot")):
            raise ValueError("user and bot are required!")

        return v

    def validate_request(self, is_scheduled: bool, event_type: EventClass):
        scheduled_events = {EventClass.message_broadcast.value, EventClass.analytics_pipeline.value}

        if is_scheduled:
            if not self.cron_exp and not self.run_at:
                raise AppException("Either cron_exp or run_at must be provided for scheduled events!")

            if self.cron_exp and self.run_at:
                raise AppException("Only one of cron_exp or run_at should be provided!")

        if is_scheduled is True and event_type not in scheduled_events:
            raise AppException(f"Only {scheduled_events} type events are allowed to be scheduled!")

        if event_type == EventClass.message_broadcast.value and Utility.check_empty_string(self.data.get("event_id")):
            raise AppException("event_id is required for message_broadcast!")


SCHEDULE_JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class ScheduleActionRequest(BaseModel):
    """
    Body of POST /api/events/schedule/action.

    The body has exactly these fields; unknown fields are rejected and string fields
    are not coerced from other JSON types. Routes must build it with `from_payload`
    so every validation failure surfaces as an AppException, which the events
    server's middleware turns into HTTP 200 {success: false, error_code: 422, message}.
    """

    job_id: StrictStr
    run_at: StrictStr
    timezone: StrictStr
    schedule_action_type: Literal["pyscript", "flow"]
    schedule_action: StrictStr
    bot: StrictStr
    user: StrictStr
    data: Dict[Text, Any]

    class Config:
        extra = Extra.forbid

    @validator("job_id")
    def validate_job_id(cls, v):
        if not SCHEDULE_JOB_ID_PATTERN.match(v):
            raise ValueError("job_id must be 32 lowercase hexadecimal characters")
        return v

    @validator("run_at")
    def validate_run_at(cls, v):
        try:
            if Utility.check_empty_string(v):
                raise ValueError("empty")
            isoparse(v)
        except (ValueError, OverflowError, TypeError):
            raise ValueError("run_at must be an ISO 8601 date-time")
        return v

    @validator("timezone")
    def validate_timezone(cls, v):
        if v != "" and v not in pytz.all_timezones_set:
            raise ValueError("timezone must be an IANA zone name or empty")
        return v

    @validator("schedule_action", "bot", "user")
    def validate_not_empty(cls, v, field):
        if Utility.check_empty_string(v):
            raise ValueError(f"{field.name} is required")
        return v

    @property
    def run_at_datetime(self) -> datetime:
        return isoparse(self.run_at)

    @classmethod
    def from_payload(cls, payload: Any) -> "ScheduleActionRequest":
        """Build the request from a decoded JSON body; any failure raises AppException."""
        if not isinstance(payload, dict):
            raise AppException("Request body must be a JSON object")
        try:
            return cls(**payload)
        except ValidationError as e:
            raise AppException(cls.format_errors(e))

    @staticmethod
    def format_errors(error: ValidationError) -> Text:
        messages = []
        for err in error.errors():
            field = ".".join(str(loc) for loc in err.get("loc", ())) or "body"
            err_type = err.get("type", "")
            if err_type in {"value_error.missing", "missing"}:
                messages.append(f"{field}: field required")
            elif err_type in {"value_error.extra", "extra_forbidden"}:
                messages.append(f"{field}: extra field not permitted")
            elif field == "schedule_action_type":
                messages.append(f"{field}: must be one of 'pyscript', 'flow'")
            else:
                msg = err.get("msg", "invalid value")
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, "):]
                messages.append(f"{field}: {msg}")
        return "; ".join(messages)
