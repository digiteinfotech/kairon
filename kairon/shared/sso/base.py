class BaseSSO:

    async def get_redirect_url(self):

        """Returns redirect url for facebook."""

        raise NotImplementedError("Provider not implemented")

    async def verify(self, request):
        """
        Fetches user details using code received in the request.

        :param request: starlette request object
        """
        raise NotImplementedError("Provider not implemented")
