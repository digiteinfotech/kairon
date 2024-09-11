from typing import Dict, Text

from kairon.events.executors.factory import ExecutorFactory
from kairon.events.scheduler.kscheduler import KScheduler
from kairon.exceptions import AppException
from kairon.shared.data.constant import TASK_TYPE


class EventUtility:

    @staticmethod
    def add_job(event_type: Text, request_data: Dict, is_scheduled: bool):
        message = None
        if is_scheduled:
            response = None
            event_id = request_data["data"]["event_id"]
            KScheduler().add_job(event_class=event_type, event_id=event_id,
                                 task_type=TASK_TYPE.EVENT.value, **request_data)
            message = 'Event Scheduled!'
        else:
            response = ExecutorFactory.get_executor().execute_task(event_class=event_type,
                                                                   task_type=TASK_TYPE.EVENT.value,
                                                                   data=request_data["data"])
        return response, message

    @staticmethod
    def update_job(event_type: Text, request_data: Dict, is_scheduled: bool):
        if not is_scheduled:
            raise AppException("Updating non-scheduled event not supported!")

        event_id = request_data["data"]["event_id"]
        KScheduler().update_job(event_class=event_type, event_id=event_id, task_type=TASK_TYPE.EVENT.value,
                                **request_data)
        return None, 'Scheduled event updated!'
