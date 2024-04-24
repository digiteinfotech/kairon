import asyncio
from asyncio import iscoroutinefunction
from typing import Callable

from AccessControl.ZopeGuards import _safe_globals
from RestrictedPython.Guards import safer_getattr

from ..actors.base import BaseActor

global_safe = _safe_globals
global_safe['_getattr_'] = safer_getattr



class CallableRunner(BaseActor):

    def execute(self, callable: Callable, *args, **kwargs):
        """
        Executes any callable as an actor.
        """
        if iscoroutinefunction(callable):
            result = asyncio.run(callable(*args, **kwargs))
        else:
            result = callable(*args, **kwargs)

        return result
