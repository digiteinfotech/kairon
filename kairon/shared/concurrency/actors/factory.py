from typing import Text

from pykka import ActorProxy

from kairon.exceptions import AppException
from .callable_runner import CallableRunner
from ..actors.pyscript_runner import PyScriptRunner
from kairon.shared.constants import ActorType


class ActorFactory:
    __actors = {
        ActorType.pyscript_runner.value: (PyScriptRunner, PyScriptRunner.start().proxy()),
        ActorType.callable_runner.value: (CallableRunner, CallableRunner.start().proxy())

    }

    @staticmethod
    def get_instance(actor_type: Text):
        if actor_type not in ActorFactory.__actors.keys():
            raise AppException(f"{actor_type} actor not implemented!")

        actor_proxy: ActorProxy = ActorFactory.__actors[actor_type][1]
        if not actor_proxy.actor_ref.is_alive():
            actor = ActorFactory.__actors[actor_type][0]
            actor_proxy = actor.start().proxy()
            ActorFactory.__actors[actor_type] = (actor, actor_proxy)

        return actor_proxy

    @staticmethod
    def stop_all():
        for _, actor in ActorFactory.__actors.values():
            actor.actor_ref.stop()
