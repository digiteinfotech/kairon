import json
from typing import Optional, Dict

import httpx
from fastapi_sso.sso.base import OpenID, SSOBase
from starlette.requests import Request

from kairon.exceptions import AppException


class LinkedinSSO(SSOBase):

    """
    Class providing login via linkedin OAuth
    """

    provider = "linkedin"
    discovery_url = "https://www.linkedin.com/oauth/v2"
    profile_url = "https://api.linkedin.com/v2"
    grant_type = "authorization_code"
    scope = 'r_liteprofile r_emailaddress'

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
        if response.get("emailAddress"):
            return OpenID(
                    email=response.get("emailAddress"),
                    provider=cls.provider,
                    id=response.get("id"),
                    first_name=response.get("localizedFirstName"),
                    last_name=response.get("localizedLastName"),
                    display_name=response.get("localizedFirstName"),
                    picture=response.get("profilePicture", {}).get("displayImage"),
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
            "userinfo_endpoint": f"{cls.profile_url}/me",
            "useremail_endpoint": f"{cls.profile_url}/emailAddress?q=members&projection=(elements*(handle~))"
        }

    async def process_login(self, code: str, request: Request) -> Optional[OpenID]:
        """
        This method should be called from callback endpoint to verify the user and request user info endpoint.
        This is low level, you should use {verify_and_process} instead.
        """
        url = request.url
        scheme = url.scheme
        if not self.allow_insecure_http and scheme != "https":
            current_url = str(url).replace("http://", "https://")
            scheme = "https"
        else:
            current_url = str(url)
        current_path = f"{scheme}://{url.netloc}{url.path}"

        token_url, headers, body = self.oauth_client.prepare_token_request(
            await self.token_endpoint, authorization_response=current_url, redirect_url=current_path, code=code
        )  # type: ignore

        if token_url is None:
            return {}

        auth = httpx.BasicAuth(self.client_id, self.client_secret)
        async with httpx.AsyncClient() as session:
            response = await session.post(token_url, headers=headers, content=body, auth=auth)
            content = response.json()
            self.oauth_client.parse_request_body_response(json.dumps(content))

            uri, headers, _ = self.oauth_client.add_token(await self.userinfo_endpoint)
            response = await session.get(uri, headers=headers)
            profile_details = response.json()

            uri, headers, _ = self.oauth_client.add_token(await self.useremail_endpoint)
            response = await session.get(uri, headers=headers)
            content = response.json()
            profile_details['emailAddress'] = content.get('elements', [{}])[0].get('handle~', {}).get('emailAddress')

        return await self.openid_from_response(profile_details)
