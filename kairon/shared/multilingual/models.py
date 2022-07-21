from pydantic import BaseModel, validator


class TranslationRequest(BaseModel):
    dest_lang: str
    translate_responses: bool = True
    translate_actions: bool = False

    @validator("dest_lang")
    def validate_dest_lang(cls, f, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(f):
            raise ValueError("dest_lang cannot be empty")
        return f
