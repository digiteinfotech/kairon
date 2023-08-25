from loguru import logger

from kairon.exceptions import AppException
from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import ActorType


class EvaluatorProcessor:

    @staticmethod
    def evaluate_pyscript(source_code: str):
        response = None
        try:
            response = ActorOrchestrator.run(ActorType.pyscript_runner.value, source_code=source_code)
        except AppException as e:
            message = f"Failed to evaluate the script: {str(e)}"
            logger.error(message)
        return response
