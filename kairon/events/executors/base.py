from abc import abstractmethod
from typing import Any

from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS, TASK_TYPE


class ExecutorBase:

    """Base class to create executors"""

    @abstractmethod
    def execute_task(self, event_class: EventClass, data: dict, **kwargs):
        raise NotImplementedError("Provider not implemented")

    def log_task(self, event_class: EventClass, task_type: TASK_TYPE, data: Any, status: EVENT_STATUS, **kwargs):
        from bson import ObjectId
        from kairon.shared.cloud.utils import CloudUtility

        executor_log_id = kwargs.pop("executor_log_id") if kwargs.get("executor_log_id") else ObjectId().__str__()
        CloudUtility.log_task(
            event_class=event_class, task_type=task_type, data=data, status=status,
            executor_log_id=executor_log_id, **kwargs
        )
        return executor_log_id
