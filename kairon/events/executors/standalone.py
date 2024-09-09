from loguru import logger

from kairon import Utility
from kairon.events.definitions.factory import EventFactory
from kairon.events.executors.base import ExecutorBase
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import EventClass, EventExecutor, ActorType


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
        logger.debug("started executing task in standalone mode")
        logger.debug(f"event_class: {event_class}, data: {data}")
        definition = EventFactory.get_instance(event_class)(**data)
        if Utility.environment['events']['executor']['type'] == EventExecutor.standalone:
            actor = ActorFactory.get_instance(ActorType.callable_runner.value)
            actor.execute(definition.execute, **data)
            msg = "Task Spawned!"
        else:
            definition.execute(**data)
        return msg
