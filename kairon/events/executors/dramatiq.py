import time

import ujson as json

from kairon.events.executors.base import ExecutorBase
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.events.broker.factory import BrokerFactory


class DramatiqExecutor(ExecutorBase):

    """
    Executor to enqueue tasks on broker which are later executed by dramatiq workers.
    """

    def execute_task(self, event_class: EventClass, data: dict, **kwargs):
        """
        Retrieves broker and enqueues message.
        """
        task_type = kwargs.get("task_type")
        start_time = time.time()
        executor_log_id = self.log_task(event_class=event_class, task_type=task_type, data=data,
                                        status=EVENT_STATUS.INITIATED, from_executor=True)
        response = {}
        try:
            msg = BrokerFactory.get_instance().enqueue(event_class, **data)
            response = json.dumps(msg.asdict())
        except Exception as e:
            exception = str(e)
            self.log_task(event_class=event_class, task_type=task_type, data=data,
                          status=EVENT_STATUS.FAIL, response=response,
                          executor_log_id=executor_log_id, elapsed_time=time.time() - start_time,
                          exception=exception, from_executor=True)
            raise AppException(exception)
        self.log_task(event_class=event_class, task_type=task_type, data=data,
                      status=EVENT_STATUS.COMPLETED, response=json.loads(response),
                      executor_log_id=executor_log_id, elapsed_time=time.time() - start_time,
                      from_executor=True)

        return response
