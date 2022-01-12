from kairon.exceptions import AppException
from kairon.shared.constants import SSO_TYPES
from kairon.shared.sso.facebook import FacebookSSOClient
from kairon.shared.sso.google import GoogleSSOClient
from kairon.shared.sso.linkedin import LinkedinSSOClient


class LoginSSOFactory:

    """
    Factory to get redirect url as well as the login token.
    """

    sso_clients = {
        SSO_TYPES.LINKEDIN.value: LinkedinSSOClient,
        SSO_TYPES.FACEBOOK.value: FacebookSSOClient,
        SSO_TYPES.GOOGLE.value: GoogleSSOClient
    }

    @staticmethod
    def get_client(sso_type: str):
        """
        Fetches user details using code received in the request.

        :param sso_type: one of supported types - google/facebook/linkedin.
        """
        if not LoginSSOFactory.sso_clients.get(sso_type):
            raise AppException(f'{sso_type} login is not supported')
        return LoginSSOFactory.sso_clients[sso_type]()
