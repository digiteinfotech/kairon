import json
from typing import Optional
from loguru import logger as logging
import httpx
from fastapi_sso.sso.base import SSOBase, OpenID
from starlette.requests import Request


class KaironSSO(SSOBase):

    async def process_login(self, code: str, request: Request) -> Optional[OpenID]:
        """This method should be called from callback endpoint to verify the user and request user info endpoint.
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
            return None

        auth = httpx.BasicAuth(self.client_id, self.client_secret)
        async with httpx.AsyncClient() as session:
            logging.debug(f'token_url: {token_url}')
            logging.debug(f'redirect_uri: {current_path}')
            logging.debug(f'request_body: {body}')
            response = await session.post(token_url, headers=headers, content=body, auth=auth)
            content = response.json()
            logging.debug(f'response: {content}')
            self.oauth_client.parse_request_body_response(json.dumps(content))

            uri, headers, _ = self.oauth_client.add_token(await self.userinfo_endpoint)
            logging.debug(f'userinfo_endpoint: {uri}')
            response = await session.get(uri, headers=headers)
            content = response.json()

        return await self.openid_from_response(content)
