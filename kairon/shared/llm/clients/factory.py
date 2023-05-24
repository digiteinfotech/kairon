from typing import Text
from kairon.exceptions import AppException
from kairon.shared.constants import LLMResourceProvider
from kairon.shared.llm.clients.azure import AzureGPT3Resources
from kairon.shared.llm.clients.gpt3 import GPT3Resources


class LLMClientFactory:
    __implementations = {
        LLMResourceProvider.openai.value: GPT3Resources,
        LLMResourceProvider.azure.value: AzureGPT3Resources
    }

    @staticmethod
    def get_resource_provider(_type: Text):
        if not LLMClientFactory.__implementations.get(_type):
            raise AppException(f'{_type} client not supported')
        return LLMClientFactory.__implementations[_type]
