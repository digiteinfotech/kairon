from loguru import logger

from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import ActorType


class EvaluatorProcessor:

    @staticmethod
    def evaluate_pyscript(source_code: str):
        message = None
        response = None
        try:
            response = ActorOrchestrator.run(ActorType.pyscript_runner.value, source_code=source_code)
        except Exception as e:
            logger.error(e)
            message = str(e)
        return response, message
