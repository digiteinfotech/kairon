from functools import partial
from types import ModuleType
from typing import Text, Dict, Optional, Callable
from datetime import datetime, date
import json
from AccessControl.ZopeGuards import _safe_globals
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safer_getattr
from loguru import logger
from timeout_decorator import timeout_decorator

from kairon.exceptions import AppException
from ..actors.base import BaseActor
from AccessControl.SecurityInfo import allow_module
from kairon.shared.concurrency.actors.utils import PyscriptUtility


allow_module("datetime")
allow_module("time")
allow_module("googlemaps")
allow_module("decimal")
allow_module("_strptime")
allow_module("orjson")

global_safe = _safe_globals
global_safe['_getattr_'] = safer_getattr
global_safe['json'] = json
global_safe['srtp_time'] = PyscriptUtility.srtptime
global_safe['srtf_time'] = PyscriptUtility.srtftime
global_safe['url_parse'] = PyscriptUtility.url_parse_quote_plus


class PyScriptRunner(BaseActor):

    def execute(self, source_code: Text, predefined_objects: Optional[Dict] = None, **kwargs):
        """
        Executes a python script. Objects(variables/callables) present in predefined_objects will be
        present as local variables and callables in the script. Any variable defined in the script
        will also be present in local dict which is returned as is from this method.
        """
        from kairon.shared.pyscript.shared_pyscript_utils import PyscriptSharedUtility

        local_vars = {}
        script_timeout = kwargs.get("timeout")
        if predefined_objects:
            local_vars = predefined_objects.copy()

        bot = predefined_objects.get("slot", {}).get("bot")

        global_safe['add_data'] = partial(PyscriptSharedUtility.add_data, bot=bot)
        global_safe['get_data'] = partial(PyscriptSharedUtility.get_data, bot=bot)
        global_safe['delete_data'] = partial(PyscriptSharedUtility.delete_data, bot=bot)
        global_safe['update_data'] = partial(PyscriptSharedUtility.update_data, bot=bot)
        global_safe['get_crud_metadata'] = partial(PyscriptSharedUtility.get_crud_metadata, bot=bot)
        global_safe['delete_schedule_job'] = partial(PyscriptSharedUtility.delete_schedule_job, bot=bot)
        global_safe['get_db_action_data'] = partial(PyscriptUtility.get_db_action_data, bot=bot,
                                                    predefined_objects=predefined_objects)
        global_safe['api_call'] = partial(PyscriptUtility.api_call, bot=bot,
                                          predefined_objects=predefined_objects)
        global_safe['send_waba_message'] = partial(PyscriptUtility.send_waba_message, bot=bot,
                                          predefined_objects=predefined_objects)
        global_safe['upload_media_to_360dialog'] = PyscriptUtility.upload_media_to_360dialog
        global_safe['fetch_media_ids'] = partial(PyscriptUtility.fetch_media_ids, bot=bot)


        @timeout_decorator.timeout(script_timeout, use_signals=False)
        def execute_script_with_timeout(src_code: Text, global_safe:Optional[Dict], local: Optional[Dict] = None):
            try:
                byte_code = compile_restricted(
                    src_code,
                    filename='<inline code>',
                    mode='exec',
                    flags=0,
                )
                exec(byte_code, global_safe, local)
                filtered_locals = self.__perform_cleanup(local_vars)
                return filtered_locals
            except Exception as e:
                logger.exception(e)
                raise AppException(f"Script execution error: {e}")

        return execute_script_with_timeout(source_code, global_safe, local_vars)

    def __perform_cleanup(self, local_vars: Dict):
        filtered_locals = {}
        for key, value in local_vars.items():
            if not isinstance(value, Callable) and not isinstance(value, ModuleType):
                if isinstance(value, datetime):
                    value = value.strftime("%m/%d/%Y, %H:%M:%S")
                elif isinstance(value, date):
                    value = value.strftime("%Y-%m-%d")
                filtered_locals[key] = value
        return filtered_locals