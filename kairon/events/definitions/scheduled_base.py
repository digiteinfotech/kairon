from abc import ABC, abstractmethod
from typing import Text, Dict

from kairon.events.definitions.base import EventsBase
from kairon.exceptions import AppException
from kairon.shared.constants import EventRequestType


class ScheduledEventsBase(EventsBase, ABC):

    def enqueue(self, event_request_type: Text, **kwargs):
        """
        Send event to event server.
        """
        request_implementation = {
            EventRequestType.trigger_async.value: self._trigger_async,
            EventRequestType.add_schedule.value: self._add_schedule,
            EventRequestType.add_one_time_schedule.value: self._add_one_time_schedule,
            EventRequestType.update_schedule.value: self._update_schedule,
            EventRequestType.resend_broadcast.value: self._resend_broadcast
        }
        if event_request_type not in request_implementation.keys():
            raise AppException(f"'{event_request_type}' is not a valid event server request!")

        return request_implementation[event_request_type](**kwargs)

    @abstractmethod
    def _trigger_async(self, config: Dict):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def _add_schedule(self, config: Dict):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def _add_one_time_schedule(self, config: Dict):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def _update_schedule(self, msg_broadcast_id: Text, config: Dict):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def _resend_broadcast(self, msg_broadcast_id: Text):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def delete_schedule(self, msg_broadcast_id: Text):
        raise NotImplementedError("Provider not implemented")
