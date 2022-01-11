from urllib.parse import urljoin

from fastapi_sso.sso.facebook import FacebookSSO

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.constants import SSO_TYPES
from kairon.shared.sso.base import BaseSSO


class FacebookSSOClient(BaseSSO):

    def __init__(self):
        Utility.check_is_enabled(SSO_TYPES.FACEBOOK.value)
        self.sso_client = FacebookSSO(
            Utility.environment["sso"][SSO_TYPES.FACEBOOK.value]["client_id"],
            Utility.environment["sso"][SSO_TYPES.FACEBOOK.value]["client_secret"],
            urljoin(Utility.environment["sso"]["redirect_url"], SSO_TYPES.FACEBOOK.value),
            allow_insecure_http=False, use_state=True
        )

    async def get_redirect_url(self):
        """
        Returns redirect url for facebook.
        """
        return await self.sso_client.get_login_redirect()

    async def verify(self, request):
        try:
            user = await self.sso_client.verify_and_process(request)
            return vars(user)
        except Exception as e:
            raise AppException(f'Failed to verify with facebook: {e}')
