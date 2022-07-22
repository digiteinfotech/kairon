from kairon import Utility
from kairon.events.executors.dramatiq import DramatiqExecutor
from kairon.events.executors.lamda import LambdaExecutor
from kairon.events.executors.standalone import StandaloneExecutor
from kairon.exceptions import AppException
from kairon.shared.constants import EventExecutor


class ExecutorFactory:

    __executors = {
        EventExecutor.aws_lambda: LambdaExecutor,
        EventExecutor.dramatiq: DramatiqExecutor,
        EventExecutor.standalone: StandaloneExecutor,
    }

    @staticmethod
    def get_executor():
        """
        Factory to retrieve instance of executor that will execute the event.
        """
        executor_type = Utility.environment['events']['executor'].get('type')
        if executor_type not in ExecutorFactory.__executors.keys():
            valid_executors = [ex.value for ex in EventExecutor]
            raise AppException(f"Executor type not configured in system.yaml. Valid types: {valid_executors}")
        return ExecutorFactory.__executors[executor_type]()
