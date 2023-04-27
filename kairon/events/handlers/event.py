from abc import ABC

from loguru import logger
from tornado.escape import json_decode, json_encode

from kairon import Utility
from kairon.events.executors.factory import ExecutorFactory
from kairon.events.scheduler.kscheduler import KScheduler
from kairon.exceptions import AppException
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
            is_scheduled = self.get_query_argument("is_scheduled", default=None, strip=False)
            logger.info(f"query_arguments={self.request.query_arguments}")
            if is_scheduled == "True" and Utility.is_valid_event_request(event_class, body):
                bot, user, event_id = body.get("bot"), body.get("user"), body.get("event_id")
                cron_exp, timezone = body.pop("cron_exp"), body.pop("timezone", None)
                KScheduler(bot, user).add_job(event_id, cron_exp, event_class, body, timezone)
                message = "Event Scheduled!"
            else:
                response = ExecutorFactory.get_executor().execute_task(event_class, body)
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))

    async def put(self, event_class: EventClass):
        success = True
        response = None
        error_code = 0
        try:
            body = json_decode(self.request.body.decode("utf8"))
            logger.info(f"request={body}")
            is_scheduled = self.get_query_argument("is_scheduled", default=None, strip=False)
            logger.info(f"query_arguments={self.request.query_arguments}")
            if is_scheduled == "True" and Utility.is_valid_event_request(event_class, body):
                bot, user, event_id = body.get("bot"), body.get("user"), body.get("event_id")
                cron_exp, timezone = body.pop("cron_exp"), body.pop("timezone", None)
                KScheduler(bot, user).update_job(event_id, cron_exp, event_class, body, timezone)
                message = "Scheduled event updated!"
            else:
                raise AppException("Updating non-scheduled event not supported!")
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))

    async def delete(self, event_class: EventClass):
        success = True
        response = None
        error_code = 0
        try:
            logger.info(f"query_arguments={self.request.query_arguments}")
            is_scheduled = self.get_query_argument("is_scheduled", default=None, strip=False)
            bot = self.get_query_argument("bot", strip=False)
            user = self.get_query_argument("user", strip=False)
            event_id = self.get_query_argument("event_id", strip=False)
            if is_scheduled == "True":
                KScheduler(bot, user).delete_job(event_id)
                message = "Scheduled event deleted!"
            else:
                raise AppException("Updating non-scheduled event not supported!")
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))
