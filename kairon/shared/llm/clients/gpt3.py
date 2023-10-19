import json
import random
from json import JSONDecodeError
from typing import Text
from loguru import logger
from openai.api_requestor import parse_stream_helper
from kairon.exceptions import AppException
from kairon.shared.constants import GPT3ResourceTypes
from kairon.shared.llm.clients.base import LLMResources
from kairon.shared.rest_client import AioRestClient


class GPT3Resources(LLMResources):
    resource_url = "https://api.openai.com/v1"

    def __init__(self, api_key: Text, **kwargs):
        self.api_key = api_key

    def get_headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    def get_resource_url(self, resource: Text):
        return f"{self.resource_url}/{resource}"

    async def invoke(self, resource: Text, model: Text, **kwargs):
        client = None
        http_url = self.get_resource_url(resource)
        request_body = kwargs.copy()
        request_body.update({"model": model})
        is_streaming_resp = kwargs.get("stream", False)
        try:
            client = AioRestClient(False)
            resp = await client.request("POST", http_url, request_body, self.get_headers(),
                                        return_json=False, is_streaming_resp=is_streaming_resp, max_retries=3)
            if resp.status != 200:
                try:
                    resp = await resp.json()
                    logger.debug(f"GPT response error: {resp}")
                    raise AppException(f"{resp['error'].get('message')}. Request id: {resp['error'].get('id')}")
                except JSONDecodeError:
                    raise AppException(f"Received non 200 status code ({resp.status}): {resp.text}")

            if is_streaming_resp:
                resp = client.streaming_response

            data = await self.__parse_response(resource, resp, **kwargs)
        finally:
            if client:
                await client.cleanup()
        return data

    async def __parse_response(self, resource: Text, response, **kwargs):
        parsers = {
            GPT3ResourceTypes.embeddings.value: self._parse_embeddings_response,
            GPT3ResourceTypes.chat_completion.value: self.__parse_completion_response
        }
        return await parsers[resource](response, **kwargs)

    async def _parse_embeddings_response(self, response, **hyperparameters):
        raw_response = await response.json()
        formatted_response = raw_response["data"][0]["embedding"]
        return formatted_response, raw_response

    async def __parse_completion_response(self, response, **kwargs):
        if kwargs.get("stream"):
            formatted_response = await self._parse_streaming_response(response, kwargs.get("n", 1))
            raw_response = response
        else:
            formatted_response, raw_response = await self._parse_api_response(response)
        return formatted_response, raw_response

    async def _parse_api_response(self, response):
        raw_response = await response.json()
        msg_choice = random.choice(raw_response['choices'])
        formatted_response = msg_choice['message']['content']
        return formatted_response, raw_response

    async def _parse_streaming_response(self, response, num_choices):
        formatted_response = ''
        msg_choice = random.randint(0, num_choices - 1)
        try:
            for chunk in response or []:
                line = parse_stream_helper(chunk)
                if line:
                    line = json.loads(line)
                    if line["choices"][0].get("index") == msg_choice and line["choices"][0]['delta'].get('content'):
                        formatted_response = f"{formatted_response}{line['choices'][0]['delta']['content']}"
        except Exception as e:
            logger.exception(e)
            raise AppException(f"Failed to parse streaming response: {chunk}")
        return formatted_response
