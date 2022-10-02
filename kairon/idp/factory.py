from kairon.exceptions import AppException
from kairon.idp.helper import IDPHelper


class IDPFactory:
    idp_supporter = {
        "idp": IDPHelper
    }

    @staticmethod
    def get_supported_idp(supporter: str):
        if not IDPFactory.idp_supporter[supporter]:
            raise AppException(f"{supporter} IDP provider not supported yet")
        return IDPFactory.idp_supporter[supporter]
