from kairon.exceptions import AppException
from kairon.utils import Utility
from mongoengine.errors import ValidationError
from mongoengine.errors import DoesNotExist
from datetime import datetime
from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    BooleanField
)


class GPT3Key(Document):
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    api_key = StringField(required=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.api_key):
            raise ValidationError("API Key cannot be empty or blank spaces")


class GPT3ApiKey:

    @staticmethod
    def add_gpt_key(user: str, api_key: str):
        if Utility.check_empty_string(api_key):
            raise AppException("APi key cannot be empty or blank spaces")
        Utility.is_exist(
            GPT3Key,
            exp_message="GPT3 token already recorded",
            user__iexact=user,
            status=True,
        )

        GPT3Key(user=user, api_key=api_key).save().to_mongo().to_dict()

    @staticmethod
    def get_user(user: str):
        try:
            return GPT3Key.objects().get(user=user).to_mongo().to_dict()
        except:
            raise DoesNotExist("GPT3 Key does not exist!")
