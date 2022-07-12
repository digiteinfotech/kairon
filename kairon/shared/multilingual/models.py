from pydantic import BaseModel, validator


class TranslationRequest(BaseModel):
    d_lang: str
    translate_responses: bool = True
    translate_actions: bool = False

    @classmethod
    @validator("d_lang")
    def validate_d_lang(cls, f, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(f):
            raise ValueError("d_lang cannot be empty")
        return f
