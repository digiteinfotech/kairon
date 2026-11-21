from urllib.parse import urljoin


from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.constants import SSO_TYPES
from kairon.shared.sso.base import BaseSSO
from kairon.shared.sso.clients.google import GoogleSSO


class GoogleSSOClient(BaseSSO):

    def __init__(self):

        """Initializes sso client if enabled else throws exception."""

        Utility.check_is_enabled(SSO_TYPES.GOOGLE.value)
        self.sso_client = GoogleSSO(
            Utility.environment["sso"][SSO_TYPES.GOOGLE.value]["client_id"],
            Utility.environment["sso"][SSO_TYPES.GOOGLE.value]["client_secret"],
            urljoin(Utility.environment["sso"]["redirect_url"], SSO_TYPES.GOOGLE.value),
            allow_insecure_http=False,
        )

    async def get_redirect_url(self):

        """Returns redirect url for facebook."""

        async with self.sso_client:
            return await self.sso_client.get_login_redirect()

    async def verify(self, request):
        try:
            async with self.sso_client:
                user = await self.sso_client.verify_and_process(request)
            return vars(user)
        except Exception as e:
            raise AppException(f'Failed to verify with google: {e}')
