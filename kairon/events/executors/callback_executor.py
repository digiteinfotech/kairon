import time
from typing import Any

import requests

from kairon import Utility
from kairon.events.executors.base import ExecutorBase
from kairon.exceptions import AppException
from kairon.shared.auth import Authentication
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import TOKEN_TYPE, EVENT_STATUS, TASK_TYPE


class CallbackExecutor(ExecutorBase):
    def execute_task(self, event_class, data: dict, **kwargs):
        """
        Executes a callback by making an HTTP POST request to a callback server.
        """
        callback_url = Utility.environment['events']['executor']['callback_executor_url']
        claims = {"sub": "action-server", "callback": True}

        token = Authentication.create_access_token(
            data=claims,
            token_type=TOKEN_TYPE.DYNAMIC.value,
            token_expire=1
        )

        payload = {
            "event_class": event_class,
            "data": data,
            "task_type": kwargs.get("task_type", "Callback"),
        }
        headers = {"Authorization": f"Bearer {token}"}

        start_time = time.time()
        task_type = payload["task_type"]
        executor_log_id = CallbackExecutor.callback_log_task(
            event_class=event_class,
            task_type=task_type,
            data=data,
            status=EVENT_STATUS.INITIATED,
            from_executor=True,
        )

        try:
            response = Utility.execute_http_request(
                "POST",
                  callback_url,
                  payload,
                  headers
            )
            CallbackExecutor.callback_log_task(
                event_class=event_class,
                task_type=task_type,
                data=data,
                status=EVENT_STATUS.COMPLETED,
                response=response,
                executor_log_id=executor_log_id,
                elapsed_time=time.time() - start_time,
                from_executor=True,
            )
            return response

        except requests.RequestException as req_err:
            CallbackExecutor.callback_log_task(
                event_class=event_class,
                task_type=task_type,
                data=data,
                status=EVENT_STATUS.FAIL,
                response={"error": str(req_err)},
                executor_log_id=executor_log_id,
                elapsed_time=time.time() - start_time,
                exception=str(req_err),
                from_executor=True,
            )
            raise AppException(f"Callback request failed: {str(req_err)}")

    @staticmethod
    def callback_log_task(event_class: EventClass, task_type: TASK_TYPE, data: Any, status: EVENT_STATUS, **kwargs):
        from bson import ObjectId
        from kairon.shared.cloud.utils import CloudUtility

        executor_log_id = kwargs.pop("executor_log_id") if kwargs.get("executor_log_id") else ObjectId().__str__()
        CloudUtility.log_task(
            event_class=event_class, task_type=task_type, data=data, status=status,
            executor_log_id=executor_log_id, **kwargs
        )
        return executor_log_id
