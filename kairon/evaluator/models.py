from pydantic import BaseModel


class EvaluatorRequest(BaseModel):
    source_code: str
