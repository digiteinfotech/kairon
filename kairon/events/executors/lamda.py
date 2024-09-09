from kairon import Utility
from kairon.events.executors.base import ExecutorBase
from kairon.exceptions import AppException
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.constants import EventClass


class LambdaExecutor(ExecutorBase):
    """
    Executor to execute the code on lambda using boto3.
    """
    def execute_task(self, event_class: EventClass, data: dict, **kwargs):
        """
        Builds event payload and triggers lambda for that particular event.
        """
        env_data = Utility.build_lambda_payload(data)
        response = CloudUtility.trigger_lambda(event_class, env_data, task_type=task_type, from_executor=True)
        if CloudUtility.lambda_execution_failed(response):
            raise AppException(response)
        return response
