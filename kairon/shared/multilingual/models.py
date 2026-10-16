from pydantic import BaseModel, field_validator


class TranslationRequest(BaseModel):
    dest_lang: str
    translate_responses: bool = True
    translate_actions: bool = False

    @field_validator("dest_lang")
    @classmethod
    def validate_dest_lang(cls, f):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(f):
            raise ValueError("dest_lang cannot be empty")
        return f
