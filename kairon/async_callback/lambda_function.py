from functools import partial

from types import ModuleType
from typing import Text, Dict, Callable

from AccessControl.ZopeGuards import _safe_globals
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safer_getattr
import orjson as json
from AccessControl.SecurityInfo import allow_module
from datetime import datetime, date
from requests import Response
from kairon.async_callback.scheduler import add_schedule_job, delete_schedule_job, generate_id
from kairon.async_callback.mail import send_email
from functools import *
from loguru import logger

allow_module("datetime")
allow_module("time")
allow_module("requests")
allow_module("googlemaps")
allow_module("_strptime")


def execute_script(source_code: Text, predefined_objects: Dict = None):
    logger.info(source_code)
    logger.info(predefined_objects)

    if not predefined_objects:
        predefined_objects = {}

    bot = predefined_objects.get("bot")

    global_safe = _safe_globals
    global_safe['_getattr_'] = safer_getattr
    global_safe['json'] = json
    global_safe['add_schedule_job'] = partial(add_schedule_job, bot=bot)
    global_safe['delete_schedule_job'] = partial(delete_schedule_job, bot=bot)
    global_safe['send_email'] = partial(send_email, bot=bot)
    global_safe["generate_id"] = generate_id

    byte_code = compile_restricted(
        source_code,
        filename='<inline code>',
        mode='exec',
        flags=0,
    )
    exec(byte_code, global_safe, predefined_objects)
    filtered_locals = perform_cleanup(predefined_objects)
    return filtered_locals


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


def lambda_handler(event, context):
    print(event)
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
        response = execute_script(data['source_code'], data.get('predefined_objects'))
        output["body"] = response
    except Exception as e:
        logger.exception(e)
        output["statusCode"] = 422
        output["body"] = str(e)

    logger.info(output)
    return output
