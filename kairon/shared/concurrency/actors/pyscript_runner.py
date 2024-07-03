from types import ModuleType
from typing import Text, Dict, Optional, Callable

import orjson as json
from AccessControl.ZopeGuards import _safe_globals
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safer_getattr
from loguru import logger
from timeout_decorator import timeout_decorator

from kairon.exceptions import AppException
from ..actors.base import BaseActor
from AccessControl.SecurityInfo import allow_module

allow_module("datetime")
allow_module("time")


global_safe = _safe_globals
global_safe['_getattr_'] = safer_getattr
global_safe['json'] = json


class PyScriptRunner(BaseActor):

    def execute(self, source_code: Text, predefined_objects: Optional[Dict] = None, **kwargs):
        """
        Executes a python script. Objects(variables/callables) present in predefined_objects will be
        present as local variables and callables in the script. Any variable defined in the script
        will also be present in local dict which is returned as is from this method.
        """
        local_vars = {}
        script_timeout = kwargs.get("timeout")
        if predefined_objects:
            local_vars = predefined_objects.copy()

        @timeout_decorator.timeout(script_timeout, use_signals=False)
        def execute_script_with_timeout(src_code: Text, local: Optional[Dict] = None):
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

        return execute_script_with_timeout(source_code, local_vars)

    def __perform_cleanup(self, local_vars: Dict):
        filtered_locals = {}
        for key, value in local_vars.items():
            if not isinstance(value, Callable) and not isinstance(value, ModuleType):
                filtered_locals[key] = value
        return filtered_locals
