from typing import Text
from loguru import logger
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.plugins.base import BasePlugin


class Gpt(BasePlugin):

    def execute(self, key: Text, prompt: Text, **kwargs):
        """
        Triggers OpenAI api to rephrase a response.

        @param key: OpenAI api token
        @param prompt: prompt to train the model
        """
        url = Utility.environment["plugins"]["gpt"]["url"]
        if Utility.check_empty_string(key) or Utility.check_empty_string(prompt):
            raise AppException("key and prompt are required to trigger gpt")
        temperature = Utility.environment['plugins']["gpt"]['temperature']
        model = Utility.environment['plugins']["gpt"]['model']
        default_max_tokens = 2 * len(prompt.split(" "))
        max_tokens = kwargs.get("max_tokens", default_max_tokens)
        headers = {"Authorization": f"Bearer {key}"}
        request_body = {"model": model, "prompt": prompt, "temperature": temperature, "max_tokens": max_tokens}
        try:
            raw_resp = Utility.execute_http_request("POST", url, headers=headers, request_body=request_body)
        except Exception as e:
            logger.exception(e)
            raw_resp = {"error": str(e)}
        return raw_resp
