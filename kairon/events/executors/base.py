from abc import abstractmethod

from mongoengine import DoesNotExist

from kairon import Utility
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS, TASK_TYPE
from kairon.shared.events.data_objects import ExecutorLogs


class ExecutorBase:

    """Base class to create executors"""

    @abstractmethod
    def execute_task(self, event_class: EventClass, data: dict, **kwargs):
        raise NotImplementedError("Provider not implemented")

    def log_task(self, event_class: EventClass, task_type: TASK_TYPE, data: dict, status: EVENT_STATUS, **kwargs):
        from bson import ObjectId

        executor_log_id = kwargs.get("executor_log_id") if kwargs.get("executor_log_id") else ObjectId().__str__()
        completion_states = [EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value]
        try:
            log = ExecutorLogs.objects(executor_log_id=executor_log_id, task_type=task_type, event_class=event_class,
                                       status__nin=completion_states).get()
        except DoesNotExist:
            log = ExecutorLogs(executor_log_id=executor_log_id, task_type=task_type, event_class=event_class)

        log.data = data if data else log.data
        log.status = status if status else log.status

        for key, value in kwargs.items():
            if not getattr(log, key, None) and Utility.is_picklable_for_mongo({key: value}):
                setattr(log, key, value)
        log.save()
        return executor_log_id

