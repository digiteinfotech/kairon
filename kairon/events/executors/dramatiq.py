import ujson as json

from kairon.events.executors.base import ExecutorBase
from kairon.shared.constants import EventClass
from kairon.shared.events.broker.factory import BrokerFactory


class DramatiqExecutor(ExecutorBase):

    """
    Executor to enqueue tasks on broker which are later executed by dramatiq workers.
    """

    def execute_task(self, event_class: EventClass, data: dict, **kwargs):
        """
        Retrieves broker and enqueues message.
        """
        msg = BrokerFactory.get_instance().enqueue(event_class, **data)
        return json.dumps(msg.asdict())
