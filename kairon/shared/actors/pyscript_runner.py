from typing import Text, Dict, Optional

from AccessControl.ZopeGuards import _safe_globals
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safer_getattr
from loguru import logger

from ..actors.base import BaseActor
from ...exceptions import AppException

global_safe = _safe_globals
global_safe['_getattr_'] = safer_getattr


class PyScriptRunner(BaseActor):

    def execute(self, source_code: Text, predefined_objects: Optional[Dict] = None, **kwargs):
        """
        Executes a python script. Objects(variables/callables) present in predefined_objects will be
        present as local variables and callables in the script. Any variable defined in the script
        will also be present in local dict which is returned as is from this method.
        """
        local = {}
        if predefined_objects:
            local = predefined_objects.copy()

        try:
            byte_code = compile_restricted(
                source_code,
                filename='<inline code>',
                mode='exec',
                flags=0,
            )
            exec(byte_code, global_safe, local)
            return local
        except Exception as e:
            logger.exception(e)
            raise AppException(f"Script execution error: {e}")
