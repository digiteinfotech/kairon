from datetime import datetime, date
from functools import partial
from types import ModuleType
from typing import Optional, Dict, Text, Callable

from RestrictedPython import compile_restricted
from loguru import logger

from kairon.exceptions import AppException
from kairon.shared.concurrency.actors.base import BaseActor
from AccessControl.ZopeGuards import _safe_globals

from kairon.shared.pyscript.callback_pyscript_utils import CallbackScriptUtility
from kairon.shared.pyscript.shared_pyscript_utils import PyscriptSharedUtility


class AnalyticsRunner(BaseActor):

    def execute(self, source_code: Text, predefined_objects: Optional[Dict] = None, **kwargs):

        predefined_objects = predefined_objects or {}
        local_vars = predefined_objects.copy()
        safe_globals = _safe_globals.copy()

        bot = predefined_objects.get("slot", {}).get("bot")

        safe_globals['add_data'] = partial(PyscriptSharedUtility.add_data, bot=bot)
        safe_globals['get_data'] = partial(PyscriptSharedUtility.get_data, bot=bot)
        safe_globals['delete_data'] = partial(PyscriptSharedUtility.delete_data, bot=bot)
        safe_globals['update_data'] = partial(PyscriptSharedUtility.update_data, bot=bot)
        safe_globals['add_analytics_raw_data'] = partial(CallbackScriptUtility.add_data_analytics, bot=bot)
        safe_globals['get_analytics_raw_data'] = partial(CallbackScriptUtility.get_data_analytics, bot=bot)
        safe_globals['processed_analytics_raw_data'] = partial(CallbackScriptUtility.mark_as_processed, bot=bot)

        try:
            byte_code = compile_restricted(
                source_code,
                filename='<inline code>',
                mode='exec'
            )
            exec(byte_code, safe_globals, local_vars)

            return self.__cleanup(local_vars)

        except Exception as e:
            logger.exception(e)
            raise AppException(f"Script execution error: {e}")

    def __cleanup(self, local_vars: Dict):
        filtered = {}
        for key, value in local_vars.items():

            if isinstance(value, Callable) or isinstance(value, ModuleType):
                continue
            if isinstance(value, datetime):
                value = value.strftime("%m/%d/%Y, %H:%M:%S")
            elif isinstance(value, date):
                value = value.strftime("%Y-%m-%d")

            filtered[key] = value

        return filtered
