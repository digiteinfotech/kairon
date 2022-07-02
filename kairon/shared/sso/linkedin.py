from urllib.parse import urljoin

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.constants import SSO_TYPES
from kairon.shared.sso.base import BaseSSO
from kairon.shared.sso.clients.linkedin import LinkedinSSO


class LinkedinSSOClient(BaseSSO):

    def __init__(self):

        """Initializes sso client if enabled else throws exception."""

        Utility.check_is_enabled(SSO_TYPES.LINKEDIN.value)
        self.sso_client = LinkedinSSO(
            Utility.environment["sso"][SSO_TYPES.LINKEDIN.value]["client_id"],
            Utility.environment["sso"][SSO_TYPES.LINKEDIN.value]["client_secret"],
            urljoin(Utility.environment["sso"]["redirect_url"], SSO_TYPES.LINKEDIN.value),
            allow_insecure_http=False, use_state=True
        )

    async def get_redirect_url(self):

        """Returns redirect url for facebook."""

        return await self.sso_client.get_login_redirect()

    async def verify(self, request):
        try:
            user = await self.sso_client.verify_and_process(request)
            return vars(user)
        except Exception as e:
            raise AppException(f'Failed to verify with linkedin: {e}')
