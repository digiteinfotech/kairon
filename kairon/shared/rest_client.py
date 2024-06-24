import asyncio
from abc import ABC
from typing import Union

from aiohttp import ClientSession, ClientTimeout, ClientResponse, ClientConnectionError
from aiohttp_retry import RetryClient, ExponentialRetry
from loguru import logger
from urllib3.util import parse_url

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.models import HttpRequestContentType
from datetime import datetime


class RestClientBase(ABC):

    async def request(self, request_method: str, http_url: str, request_body: Union[dict, list] = None,
                      headers: dict = None, return_json: bool = True, **kwargs):
        raise NotImplementedError("Provider not implemented!")

    async def cleanup(self):
        raise NotImplementedError("Provider not implemented!")


class AioRestClient(RestClientBase):

    def __init__(self, close_session_with_rqst_completion=True):
        self.session = ClientSession()
        self.close_session_with_rqst_completion = close_session_with_rqst_completion
        self._streaming_response = None
        self._time_elapsed = None
        self._status_code = None

    @property
    def streaming_response(self):
        return self._streaming_response

    @streaming_response.setter
    def streaming_response(self, resp):
        self._streaming_response = resp

    @property
    def time_elapsed(self):
        return self._time_elapsed

    @time_elapsed.setter
    def time_elapsed(self, time_elapsed):
        self._time_elapsed = time_elapsed.microseconds / 1000

    @property
    def status_code(self):
        return self._status_code

    @status_code.setter
    def status_code(self, status_code):
        self._status_code = status_code

    async def request(self, request_method: str, http_url: str, request_body: Union[dict, list] = None,
                      headers: dict = None,
                      return_json: bool = True, **kwargs):
        max_retries = kwargs.get("max_retries", 1)
        status_forcelist = set(kwargs.get("status_forcelist", [104, 502, 503, 504]))
        timeout = ClientTimeout(total=kwargs['timeout']) if kwargs.get('timeout') else None
        is_streaming_resp = kwargs.pop("is_streaming_resp", False)
        content_type = kwargs.pop("content_type", HttpRequestContentType.json.value)
        headers = headers if headers else {}
        request_body = request_body if request_body else {}

        retry_options = ExponentialRetry(attempts=max_retries, statuses=status_forcelist)
        response: ClientResponse = await self.__trigger_request(request_method, http_url, retry_options, request_body,
                                                                headers, content_type, timeout, is_streaming_resp)
        self.__validate_response(response, **kwargs)
        if not is_streaming_resp and return_json:
            response = await response.json()

        return response

    async def __trigger_request(self, request_method: str, http_url: str, retry_options: ExponentialRetry,
                                request_body: Union[dict, list] = None, headers: dict = None,
                                content_type: str = HttpRequestContentType.json.value,
                                timeout: ClientTimeout = None, is_streaming_resp: bool = False) -> ClientResponse:
        client = RetryClient(self.session, raise_for_status=True, retry_options=retry_options)
        try:
            logger.info(f"Event started: {http_url}")
            if request_method.lower() in ['get', 'delete']:
                request_body.update({k: '' for k, v in request_body.items() if not v})
                request_body.update({k: f'{v}' for k, v in request_body.items() if not isinstance(v, (str, int, float))})
                response = await self.__trigger(client, request_method.upper(), http_url, headers=headers,
                                                params=request_body, timeout=timeout, is_streaming_resp=is_streaming_resp)
            elif request_method.lower() in ['post', 'put']:
                kwargs = {content_type: request_body}
                response = await self.__trigger(client, request_method.upper(), http_url, headers=headers,
                                                timeout=timeout, is_streaming_resp=is_streaming_resp, **kwargs)
            else:
                raise AppException("Invalid request method!")
            return response
        except ClientConnectionError as e:
            logger.exception(e)
            _, _, host, _, _, _, _ = parse_url(http_url)
            self.status_code = 503
            raise AppException(f"Failed to connect to service: {host}")
        except asyncio.TimeoutError as e:
            logger.exception(e)
            self.status_code = 408
            raise AppException(f"Request timed out: {str(e)}")
        except Exception as e:
            logger.exception(e)
            self.status_code = 500
            raise AppException(f"Failed to execute the url: {str(e)}")
        finally:
            if self.close_session_with_rqst_completion:
                await client.close()

    async def __trigger(self, client, *args, **kwargs) -> ClientResponse:
        """
        Trigger request and aggregate streaming response if is_streaming_resp is True.
        Response object is returned as it is and Streaming response is set into class property.
        """
        is_streaming_resp = kwargs.pop("is_streaming_resp", False)
        rqst_start_time = datetime.utcnow()
        async with client.request(*args, **kwargs) as response:
            self.time_elapsed = datetime.utcnow() - rqst_start_time
            logger.debug(f"Content-type: {response.headers['content-type']}")
            logger.debug(f"Status code: {str(response.status)}")
            self.status_code = response.status
            if is_streaming_resp:
                streaming_resp = await AioRestClient.parse_streaming_response(response)
                self.streaming_response = streaming_resp
                logger.debug(f"Raw streaming response: {streaming_resp}")
            text = await response.text()
            logger.debug(f"Raw response: {text}")
            return response

    def __validate_response(self, response: ClientResponse, **kwargs):
        """
        Validate response status based on arguments passed to the method.
        validate_status: whether to validate status code
        expected_status_code: status codes which are desired as response status code.
        err_msg: If actual status code is not found in expected set, then this message is raised.
        """
        if kwargs.get('validate_status', False) and response.status not in kwargs.get('expected_status_code', {200, 201, 202, 204}):
            if Utility.check_empty_string(kwargs.get('err_msg')):
                raise AppException("err_msg cannot be empty")
            raise AppException(f"{kwargs['err_msg']}{response.reason}")

    async def cleanup(self):
        """
        Close underlying connector to release all acquired resources.
        """
        if not self.session.closed:
            await self.session.close()

    @staticmethod
    async def parse_streaming_response(response):
        chunks = []
        async for chunk in response.content:
            if not chunk:
                break
            chunks.append(chunk)

        return chunks
