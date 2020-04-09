from typing import Text, List, Dict
from mongoengine.document import BaseDocument
class Utility:

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
                example = example.replace(entity['value'], '[' + entity['value'] + '](' + entity['entity'] + ')')
        return example

    @staticmethod
    def validate_document_list(documents: List[BaseDocument]):
        for document in documents:
            document.validate()