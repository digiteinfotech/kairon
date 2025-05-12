import requests

from kairon import Utility
from kairon.events.executors.base import ExecutorBase
from kairon.exceptions import AppException


class CallbackExecutor(ExecutorBase):
    def execute_task(self, event_class, data: dict, **kwargs):
        """
        Executes a callback by making an HTTP POST request to a callback server.
        """
        callback_url = Utility.environment['events']['executor']['callback_executor_url']
        payload = {
            "event_class": event_class,
            "data": data,
            "task_type": kwargs.get("task_type", "Callback"),
        }

        try:
            response = Utility.execute_http_request(
                "POST",
                  callback_url,payload
            )
            return response

        except requests.RequestException as req_err:
            raise AppException(f"Callback request failed: {str(req_err)}")
