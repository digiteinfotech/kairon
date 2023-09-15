from typing import Text

import pykka

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.concurrency.actors.factory import ActorFactory


class ActorOrchestrator:

    @staticmethod
    def run(actor_type: Text, *args, **kwargs):
        actor = ActorFactory.get_instance(actor_type)
        actor_timeout = kwargs.get("timeout")
        try:
            future = actor.execute(*args, **kwargs)
            result = future.get(actor_timeout)
            return result
        except pykka._exceptions.Timeout as e:
            raise AppException(f"Operation timed out: {e}")
        finally:
            actor.actor_ref.stop()
