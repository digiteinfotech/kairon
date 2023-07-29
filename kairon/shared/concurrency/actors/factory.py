from typing import Text

from kairon.exceptions import AppException
from ..actors.pyscript_runner import PyScriptRunner
from kairon.shared.constants import ActorTypes


class ActorFactory:

    __actors = {
        ActorTypes.pyscript_runner: PyScriptRunner
    }

    @staticmethod
    def get_instance(actor_type: Text):
        if actor_type not in ActorFactory.__actors.keys():
            raise AppException(f"{actor_type} actor not implemented!")

        return ActorFactory.__actors[actor_type].start().proxy()
