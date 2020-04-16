from typing import Text, List, Dict
from mongoengine.document import BaseDocument, Document
import os
import yaml
from mongoengine import StringField, ListField
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from bot_trainer.exceptions import AppException


class Utility:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
    environment = None

    @staticmethod
    def check_empty_string(value: str):
        if not value:
            return True
        if not value.strip():
            return True
        else:
            return False

    @staticmethod
    def prepare_nlu_text(example: Text, entities: List[Dict]):
        if not Utility.check_empty_string(example):
            for entity in entities:
                example = example.replace(
                    entity["value"],
                    "[" + entity["value"] + "](" + entity["entity"] + ")",
                )
        return example

    @staticmethod
    def validate_document_list(documents: List[BaseDocument]):
        for document in documents:
            document.validate()

    @staticmethod
    def load_yaml(file: Text):
        with open(file) as fp:
            return yaml.load(fp, yaml.FullLoader)

    @staticmethod
    def load_evironment():
        environment = Utility.load_yaml(os.getenv("system_file", "./system.yaml"))
        for key in environment:
            if key in os.environ:
                environment[key] = os.getenv(key)
        Utility.environment = environment

    @staticmethod
    def validate_fields(fields: Dict, data: Dict):
        error = ""
        for key, value in fields.items():
            if isinstance(value, StringField):
                if data[key] != None and str(data["key"]).strip():
                    error += "\n " + key + " cannot be empty or blank spaces"
            elif isinstance(value, ListField):
                if value.required and value:
                    error += "\n " + key + " cannot be empty"
        if error:
            raise error

    @staticmethod
    def is_exist(
        document: Document, query: Dict, exp_message: Text = None, raise_error=True,
    ):
        doc = document.objects(status=True, __raw__=query)
        if doc.__len__():
            if raise_error:
                if Utility.check_empty_string(exp_message):
                    raise AppException("Exception message cannot be empty")
                raise AppException(exp_message)
            else:
                return True
        else:
            if not raise_error:
                return False

    @staticmethod
    def verify_password(plain_password, hashed_password):
        return Utility.pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password):
        if not Utility.check_empty_string(password):
            return Utility.pwd_context.hash(password)
