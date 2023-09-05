from typing import Dict, Text

from kairon.events.executors.factory import ExecutorFactory
from kairon.events.scheduler.kscheduler import KScheduler
from kairon.exceptions import AppException


class EventUtility:

    @staticmethod
    def add_job(event_type: Text, request_data: Dict, is_scheduled: bool):
        message = None
        if is_scheduled:
            event_id = request_data["data"]["event_id"]
            response = KScheduler().add_job(event_class=event_type, event_id=event_id, **request_data)
            message = 'Event Scheduled!'
        else:
            response = ExecutorFactory.get_executor().execute_task(event_type, request_data["data"])
        return response, message

    @staticmethod
    def update_job(event_type: Text, request_data: Dict, is_scheduled: bool):
        if not is_scheduled:
            raise AppException("Updating non-scheduled event not supported!")

        event_id = request_data["data"]["event_id"]
        response = KScheduler().update_job(event_class=event_type, event_id=event_id, **request_data)
        message = 'Scheduled event updated!'
        return response, message
