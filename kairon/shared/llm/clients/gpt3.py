import json
import random
from json import JSONDecodeError
from typing import Text
from loguru import logger
from openai.api_requestor import parse_stream
from kairon.exceptions import AppException
from kairon.shared.constants import GPT3ResourceTypes
from kairon.shared.llm.clients.base import LLMResources
from kairon.shared.utils import Utility


class GPT3Resources(LLMResources):
    resource_url = "https://api.openai.com/v1"

    def __init__(self, api_key: Text, **kwargs):
        self.api_key = api_key

    def get_headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    def get_resource_url(self, resource: Text):
        return f"{self.resource_url}/{resource}"

    def invoke(self, resource: Text, model: Text, **kwargs):
        http_url = self.get_resource_url(resource)
        request_body = kwargs.copy()
        request_body.update({"model": model})
        resp = Utility.execute_http_request(
            "POST", http_url, request_body, self.get_headers(), max_retries=3, backoff_factor=0.2, return_json=False
        )
        if resp.status_code != 200:
            try:
                resp = resp.json()
                logger.debug(f"GPT response error: {resp}")
                raise AppException(f"{resp['error'].get('message')}. Request id: {resp['error'].get('id')}")
            except JSONDecodeError:
                raise AppException(f"Received non 200 status code: {resp.text}")

        return self.__parse_response(resource, resp, **kwargs)

    def __parse_response(self, resource: Text, response, **kwargs):
        parsers = {
            GPT3ResourceTypes.embeddings.value: self._parse_embeddings_response,
            GPT3ResourceTypes.chat_completion.value: self.__parse_completion_response
        }
        return parsers[resource](response, **kwargs)

    def _parse_embeddings_response(self, response, **hyperparameters):
        raw_response = response.json()
        formatted_response = raw_response["data"][0]["embedding"]
        return formatted_response, raw_response

    def __parse_completion_response(self, response, **kwargs):
        if kwargs.get("stream"):
            formatted_response, raw_response = self._parse_streaming_response(response, kwargs.get("n", 1))
        else:
            formatted_response, raw_response = self._parse_api_response(response)
        return formatted_response, raw_response

    def _parse_streaming_response(self, response, num_choices):
        line = None
        formatted_response = ''
        raw_response = []
        msg_choice = random.randint(0, num_choices - 1)
        try:
            for line in parse_stream(response.iter_lines()):
                line = json.loads(line)
                if line["choices"][0].get("index") == msg_choice and line["choices"][0]['delta'].get('content'):
                    formatted_response = f"{formatted_response}{line['choices'][0]['delta']['content']}"
                raw_response.append(line)
        except (JSONDecodeError, UnicodeDecodeError) as e:
            logger.exception(e)
            raise AppException(f"Received HTTP code {response.status_code} in streaming response from openai: {line}")
        except Exception as e:
            logger.exception(e)
            raise AppException(f"Failed to parse response: {line}")
        return formatted_response, raw_response

    def _parse_api_response(self, response):
        raw_response = response.json()
        msg_choice = random.choice(raw_response['choices'])
        formatted_response = msg_choice['message']['content']
        return formatted_response, raw_response
