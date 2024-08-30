import ujson as json
from typing import Optional, Dict, Any, Union, Literal

import httpx
from fastapi_sso.sso.base import OpenID
from starlette.requests import Request
from loguru import logger as logging
from kairon.exceptions import AppException
from kairon.shared.sso.clients.kairon import KaironSSO


class LinkedinSSO(KaironSSO):

    """
    Class providing login via linkedin OAuth
    """

    provider = "linkedin"
    discovery_url = "https://www.linkedin.com/oauth/v2"
    profile_url = "https://api.linkedin.com/v2"
    grant_type = "authorization_code"
    scope = 'profile email openid'

    @property
    async def useremail_endpoint(self) -> Optional[str]:
        """
        Return `useremail_endpoint` from discovery document.
        """
        discovery = await self.get_discovery_document()
        return discovery.get("useremail_endpoint")

    @classmethod
    async def openid_from_response(cls, response: dict) -> OpenID:
        """
        Returns user details.
        """
        if response.get("email"):
            return OpenID(
                    email=response.get("email"),
                    provider=cls.provider,
                    id=response.get("sub"),
                    first_name=response.get("given_name"),
                    last_name=response.get("family_name"),
                    display_name=response.get("name"),
                    picture=response.get("picture"),
                )

        raise AppException("User was not verified with linkedin")

    @classmethod
    async def get_discovery_document(cls) -> Dict[str, str]:
        """
        Get document containing handy urls.
        """
        return {
            "authorization_endpoint": f"{cls.discovery_url}/authorization",
            "token_endpoint": f"{cls.discovery_url}/accessToken",
            "userinfo_endpoint": f"{cls.profile_url}/userinfo"
        }

    async def process_login(
            self,
            code: str,
            request: Request,
            *,
            params: Optional[Dict[str, Any]] = None,
            additional_headers: Optional[Dict[str, Any]] = None,
            redirect_uri: Optional[str] = None,
            pkce_code_verifier: Optional[str] = None,
            convert_response: Union[Literal[True], Literal[False]] = True,
    ) -> Optional[OpenID]:
        """
        This method should be called from callback endpoint to verify the user and request user info endpoint.
        This is low level, you should use {verify_and_process} instead.
        """
        url = request.url
        scheme = url.scheme
        if not self.allow_insecure_http and scheme != "https":
            current_url = str(url).replace("http://", "https://")
        else:
            current_url = str(url)
        current_path = self.redirect_uri

        token_url, headers, body = self.oauth_client.prepare_token_request(
            await self.token_endpoint, authorization_response=current_url, redirect_url=current_path, code=code
        )  # type: ignore

        if token_url is None:
            return {}

        auth = httpx.BasicAuth(self.client_id, self.client_secret)
        async with httpx.AsyncClient() as session:
            body = body + f"&client_secret={self.client_secret}"
            response = await session.post(token_url, headers=headers, content=body, auth=auth)
            content = response.json()
            logging.info(f'response: {content}')
            self.oauth_client.parse_request_body_response(json.dumps(content))

            uri, headers, _ = self.oauth_client.add_token(await self.userinfo_endpoint)
            response = await session.get(uri, headers=headers)
            profile_details = response.json()

            return await self.openid_from_response(profile_details)
