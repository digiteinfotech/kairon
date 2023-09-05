from typing import Text, Dict

from pydantic import BaseModel, validator

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass


class EventRequest(BaseModel):
    data: Dict
    cron_exp: Text = None
    timezone: Text = None

    class Config:
        use_enum_values = True

    @validator("data")
    def validate_data(cls, v, values, **kwargs):
        if Utility.check_empty_string(v.get("user")) or Utility.check_empty_string(v.get("bot")):
            raise ValueError("user and bot are required!")

        return v

    def validate_request(self, is_scheduled: bool, event_type: EventClass):
        scheduled_events = {EventClass.message_broadcast.value}

        if is_scheduled is True and Utility.check_empty_string(self.cron_exp):
            raise AppException("cron_exp is required for scheduled events!")

        if is_scheduled is True and event_type not in scheduled_events:
            raise AppException(f"Only {scheduled_events} type events are allowed to be scheduled!")

        if event_type == EventClass.message_broadcast.value and Utility.check_empty_string(self.data.get("event_id")):
            raise AppException("event_id is required for message_broadcast!")
