from pydantic import BaseModel, validator


class EvaluatorRequest(BaseModel):
    source_code: str
    predefined_objects: dict = None

    @validator("source_code")
    def validate_source_code(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("source_code is required")
        return v
