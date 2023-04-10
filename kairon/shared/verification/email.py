import requests
from kairon.shared.verification.base import Verification
from kairon.shared.utils import Utility


class QuickEmailVerification(Verification):
    def __init__(self):
        self.url = "http://api.quickemailverification.com/v1/verify"
        self.key = Utility.environment["verify"]["email"]["key"]
        self.headers = {"content-type": "application/json"}

    def verify(self, value: str, *args, **kwargs) -> bool:
        params = {"apikey": self.key, "email": value}
        response = requests.get(self.url, headers=self.headers, params=params).json()
        return (response.get('result') == "valid" and
                response.get("disposable") == "false")


class EmailVerficationFactory():
    verify = {"quickemail": QuickEmailVerification}

    @staticmethod
    def get_instance():
        return EmailVerficationFactory.verify[Utility.environment["verify"]["email"]["type"]]()
