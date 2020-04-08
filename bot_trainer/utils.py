import yaml
from typing import Text, List, Dict

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