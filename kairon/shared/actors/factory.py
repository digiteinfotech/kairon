from typing import Text

from ..actors.pyscript_runner import PyScriptRunner
from ..constants import ActorTypes


class ActorFactory:

    __actors = {
        ActorTypes.pyscript_runner: PyScriptRunner.start().proxy()
    }

    @staticmethod
    def get_instance(actor_type: Text):
        return ActorFactory.__actors[actor_type]
