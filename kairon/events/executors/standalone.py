import time

from loguru import logger

from kairon import Utility
from kairon.events.definitions.factory import EventFactory
from kairon.events.executors.base import ExecutorBase
from kairon.exceptions import AppException
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import EventClass, EventExecutor, ActorType
from kairon.shared.data.constant import EVENT_STATUS


class StandaloneExecutor(ExecutorBase):
    """
    Standalone executor to execute tasks either in background or in a synchronous fashion.
    Events are executed in background when event server runs on standalone mode.
    Events are executed in synchronous fashion when used with dramatiq.
    It is recommended that this type of executor should only be used with workers.
    """

    def execute_task(self, event_class: EventClass, data: dict, **kwargs):
        """
        Executes events based on the event class received.
        """
        msg = None
        task_type = kwargs.get("task_type")
        start_time = time.time()
        logger.debug("started executing task in standalone mode")
        logger.debug(f"event_class: {event_class}, data: {data}")
        executor_log_id = self.log_task(event_class=event_class, task_type=task_type, data=data,
                                        status=EVENT_STATUS.INITIATED, from_executor=True)
        definition = EventFactory.get_instance(event_class)(**data)
        try:
            if Utility.environment['events']['executor']['type'] == EventExecutor.standalone:
                actor = ActorFactory.get_instance(ActorType.callable_runner.value)
                actor.execute(definition.execute, **data)
                msg = "Task Spawned!"
            else:
                definition.execute(**data)
        except Exception as e:
            exception = str(e)
            self.log_task(event_class=event_class, task_type=task_type, data=data,
                          status=EVENT_STATUS.FAIL, response=msg,
                          executor_log_id=executor_log_id, elapsed_time=time.time() - start_time,
                          exception=exception, from_executor=True)
            raise AppException(exception)
        self.log_task(event_class=event_class, task_type=task_type, data=data,
                      status=EVENT_STATUS.COMPLETED, response={"message": msg},
                      executor_log_id=executor_log_id, elapsed_time=time.time() - start_time,
                      from_executor=True)
        return msg
