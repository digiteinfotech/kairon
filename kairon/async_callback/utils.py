from datetime import datetime, date
from blacksheep import JSONContent, TextContent, Response as BSResponse
from requests import Response
from functools import partial
from types import ModuleType
from typing import Text, Dict, Callable
import requests
from AccessControl.SecurityInfo import allow_module
from RestrictedPython.Guards import safer_getattr
import orjson as json
from loguru import logger
from kairon.api.app.routers.bot.data import CognitionDataProcessor
from kairon.shared.callback.data_objects import CallbackResponseType
from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import ActorType


from kairon.shared.pyscript.callback_pyscript_utils import CallbackScriptUility
from kairon.shared.pyscript.shared_pyscript_utils import PyscriptSharedUtility

allow_module("datetime")
allow_module("time")
allow_module("requests")
allow_module("googlemaps")
allow_module("_strptime")
cognition_processor = CognitionDataProcessor()




class CallbackUtility:

    @staticmethod
    def perform_cleanup(local_vars: Dict):
        logger.info(f"local_vars: {local_vars}")
        filtered_locals = {}
        if local_vars:
            for key, value in local_vars.items():
                if not isinstance(value, Callable) and not isinstance(value, ModuleType):
                    if isinstance(value, datetime):
                        value = value.strftime("%m/%d/%Y, %H:%M:%S")
                    elif isinstance(value, date):
                        value = value.strftime("%Y-%m-%d")
                    elif isinstance(value, Response):
                        value = value.text
                    filtered_locals[key] = value
        logger.info(f"filtered_vars: {filtered_locals}")
        return filtered_locals

    @staticmethod
    def execute_script(source_code: Text, predefined_objects: Dict = None):
        logger.info(source_code)
        logger.info(predefined_objects)

        if not predefined_objects:
            predefined_objects = {}

        bot = predefined_objects.get("bot")
        channel = predefined_objects.get("channel")
        sender_id = predefined_objects.get("sender_id")

        predefined_objects['_getattr_'] = safer_getattr
        predefined_objects['requests']=requests
        predefined_objects['json'] = json
        predefined_objects['datetime']= datetime
        predefined_objects['add_schedule_job'] = partial(CallbackScriptUility.add_schedule_job, bot=bot)
        predefined_objects['delete_schedule_job'] = partial(PyscriptSharedUtility.delete_schedule_job, bot=bot)
        predefined_objects['send_email'] = partial(CallbackScriptUility.send_email, bot=bot)
        predefined_objects['add_data'] = partial(PyscriptSharedUtility.add_data, bot=bot)
        predefined_objects['get_data'] = partial(PyscriptSharedUtility.get_data, bot=bot)
        predefined_objects['delete_data'] = partial(PyscriptSharedUtility.delete_data, bot=bot)
        predefined_objects['update_data'] = partial(PyscriptSharedUtility.update_data, bot=bot)
        predefined_objects["generate_id"] = CallbackScriptUility.generate_id
        predefined_objects["datetime_to_utc_timestamp"]=CallbackScriptUility.datetime_to_utc_timestamp
        predefined_objects['decrypt_request'] = CallbackScriptUility.decrypt_request
        predefined_objects['encrypt_response'] = CallbackScriptUility.encrypt_response
        predefined_objects['create_callback'] = partial(CallbackScriptUility.create_callback,
                                                            bot=bot,
                                                            sender_id=sender_id,
                                                           channel=channel)
        predefined_objects['save_as_pdf'] = partial(CallbackScriptUility.save_as_pdf,
                                                            bot=bot, sender_id=sender_id)
        script_variables = ActorOrchestrator.run(
            ActorType.pyscript_runner.value, source_code=source_code, timeout=60,
            predefined_objects=predefined_objects
        )
        return script_variables

    @staticmethod
    def pyscript_handler(event, context):
        output = {
            "statusCode": 200,
            "statusDescription": "200 OK",
            "isBase64Encoded": False,
            "headers": {
                "Content-Type": "text/html; charset=utf-8"
            },
            "body": None
        }
        data = event
        if isinstance(data, list):
            data = {item['name'].lower(): item['value'] for item in data}
        try:
            response = CallbackUtility.execute_script(data['source_code'], data.get('predefined_objects'))
            output["body"] = response
        except Exception as e:
            logger.exception(e)
            output["statusCode"] = 422
            output["body"] = str(e)

        logger.info(output)
        return output

    @staticmethod
    def execute_main_pyscript(source_code: Text, predefined_objects: Dict = None):
        logger.info(source_code)
        logger.info(predefined_objects)

        if not predefined_objects:
            predefined_objects = {}


        script_variables = ActorOrchestrator.run(
            ActorType.pyscript_runner.value, source_code=source_code, timeout=60,
            predefined_objects=predefined_objects
        )
        return script_variables

    @staticmethod
    def main_pyscript_handler(event, context):
        output = {
            "statusCode": 200,
            "statusDescription": "200 OK",
            "isBase64Encoded": False,
            "headers": {
                "Content-Type": "text/html; charset=utf-8"
            },
            "body": None
        }
        data = event
        if isinstance(data, list):
            data = {item['name'].lower(): item['value'] for item in data}
        try:
            response = CallbackUtility.execute_main_pyscript(data['source_code'], data.get('predefined_objects'))
            output["body"] = response
        except Exception as e:
            logger.exception(e)
            output["statusCode"] = 422
            output["body"] = str(e)

        logger.info(output)
        return output

    @staticmethod
    def return_response(data: any, message : str, error_code: int, response_type: str):
        resp_status_code = 200 if error_code == 0 else 422
        if response_type == CallbackResponseType.KAIRON_JSON.value:
            return BSResponse(
                status=resp_status_code,
                content=JSONContent({
                    "message": message,
                    "data": data,
                    "error_code": error_code,
                    "success": error_code == 0,
                })
            )
        elif response_type == CallbackResponseType.JSON.value:
            return BSResponse(
                status=resp_status_code,
                content=JSONContent(data)
            )
        elif response_type == CallbackResponseType.TEXT.value:
            return BSResponse(
                status=resp_status_code,
                content=TextContent(str(data))
            )


