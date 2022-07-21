from abc import ABC

from loguru import logger
from tornado.escape import json_decode, json_encode

from kairon.events.executors.factory import ExecutorFactory
from kairon.shared.constants import EventClass
from kairon.shared.tornado.handlers.base import BaseHandler


class EventHandler(BaseHandler, ABC):

    async def post(self, event_class: EventClass):
        success = True
        message = None
        response = None
        error_code = 0
        try:
            body = json_decode(self.request.body.decode("utf8"))
            logger.info(f"request={body}")
            response = ExecutorFactory.get_executor().execute_task(event_class, body)
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))
