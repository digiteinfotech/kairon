from typing import Text

from kairon.shared.concurrency.actors.factory import ActorFactory


class ActorOrchestrator:

    @staticmethod
    def run(actor_type: Text, **kwargs):
        actor = ActorFactory.get_instance(actor_type)
        actor_timeout = kwargs.pop("timeout", None)
        try:
            future = actor.execute(**kwargs)
            result = future.get(actor_timeout)
            return result
        finally:
            actor.actor_ref.stop()
