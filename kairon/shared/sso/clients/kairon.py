import ujson as json
from typing import Optional, Dict, Any, Union, Literal
from loguru import logger as logging
import httpx
from fastapi_sso.sso.base import SSOBase, OpenID
from starlette.requests import Request


class KaironSSO(SSOBase):

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
        """This method should be called from callback endpoint to verify the user and request user info endpoint.
        This is low level, you should use {verify_and_process} instead.
        """
        logging.debug(f'redirect_uri: {self.redirect_uri}')
        current_path = f'{self.redirect_uri}?code={code}'
        logging.debug(f'current_path with query_params: {current_path}')
        if self.state is not None and self.use_state and request.query_params.get("state"):
            current_path = f'{current_path}&state={request.query_params.get("state")}'
        logging.debug(f'current_path with query_params: {current_path}')
        token_url, headers, body = self.oauth_client.prepare_token_request(
            await self.token_endpoint, authorization_response=current_path, redirect_url=self.redirect_uri, code=code
        )  # type: ignore

        if token_url is None:
            return None

        auth = httpx.BasicAuth(str(self.client_id), self.client_secret)
        async with httpx.AsyncClient() as session:
            logging.debug(f'token_url: {token_url}')
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
