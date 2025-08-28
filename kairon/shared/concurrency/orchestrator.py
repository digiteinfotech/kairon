from typing import Text

import pykka

from kairon.exceptions import AppException
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import ActorType


class ActorOrchestrator:

    @staticmethod
    def run(actor_type: Text, *args, **kwargs):
        actor = ActorFactory.get_instance(actor_type)
        actor_timeout = kwargs.get("timeout")
        retries = kwargs.get("retries", 1)
        try:
            for attempt in range(1, retries + 1):
                try:
                    future = actor.execute(*args, **kwargs)
                    result = future.get(actor_timeout)
                    return result
                except pykka._exceptions.Timeout as e:
                    raise AppException(f"Operation timed out: {e}")
                except Exception as e:
                    if attempt == retries:
                        raise AppException(
                            f"{e}"
                        )
        finally:
            actor.actor_ref.stop()