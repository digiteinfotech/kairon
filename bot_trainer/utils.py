import yaml

class Utility:

    @staticmethod
    def check_empty_string(value: str):
        if not value:
            return True
        if not value.strip():
            return True
        else:
            return False