from typing import Text

import pykka
from loguru import logger
from kairon.exceptions import AppException
from kairon.shared.concurrency.actors.factory import ActorFactory



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
                    logger.error(f"Actor '{actor_type}' execution timed out after {actor_timeout} seconds "
                                 f"(attempt {attempt}/{retries})")
                    raise AppException(f"Operation timed out: {e}") from e

                except pykka._exceptions.ActorDeadError as e:
                    logger.warning(f"Actor '{actor_type}' died during execution (attempt {attempt}/{retries}): {e}")
                    try:
                        actor.actor_ref.stop()
                    except Exception as e:
                        logger.warning(f"Failed to stop actor '{actor_type}': {e}")
                    actor = ActorFactory.get_instance(actor_type)
                    if attempt == retries:
                        logger.error(f"All {retries} attempts failed due to dead actor '{actor_type}'")
                        raise AppException(
                            str(e)
                        ) from e
                except Exception as e:
                    logger.error(f"Unexpected error in actor '{actor_type}' "
                                 f"(attempt {attempt}/{retries}): {e}")
                    if attempt == retries:
                        raise AppException(
                            str(e)
                        ) from e
        finally:
            try:
                actor.actor_ref.stop()
                logger.debug(f"Actor '{actor_type}' stopped")
            except Exception as stop_err:
                logger.warning(f"Failed to stop actor '{actor_type}': {stop_err}")