from fastapi import APIRouter

from kairon.api.models import Response
from kairon.evaluator.models import EvaluatorRequest
from kairon.evaluator.processor import EvaluatorProcessor

router = APIRouter()


@router.post("/evaluate", response_model=Response)
def run_pyscript(request_data: EvaluatorRequest):
    response, message = EvaluatorProcessor.evaluate_pyscript(source_code=request_data.source_code)
    return {"data": response, "message": message}
