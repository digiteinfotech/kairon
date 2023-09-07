from loguru import logger

from kairon.exceptions import AppException
from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import ActorType


class EvaluatorProcessor:

    @staticmethod
    def evaluate_pyscript(source_code: str, predefined_objects: dict = None):
        try:
            response = ActorOrchestrator.run(ActorType.pyscript_runner.value, source_code=source_code,
                                             predefined_objects=predefined_objects)
        except AppException as e:
            message = str(e)
            logger.error(message)
            raise AppException(message)
        return response
