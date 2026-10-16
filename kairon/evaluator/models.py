from pydantic import BaseModel, field_validator


class EvaluatorRequest(BaseModel):
    source_code: str
    predefined_objects: dict = None

    @field_validator("source_code")
    @classmethod
    def validate_source_code(cls, v):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("source_code is required")
        return v
