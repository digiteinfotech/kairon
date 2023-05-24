from typing import Text

from kairon.shared.constants import GPT3ResourceTypes
from kairon.shared.llm.clients.gpt3 import GPT3Resources


class AzureGPT3Resources(GPT3Resources):
    resource_url = "https://kairon.openai.azure.com/openai/deployments"

    def __init__(self, api_key: Text, **kwargs):
        super().__init__(api_key)
        self.api_key = api_key
        self.api_version = kwargs.get("api_version")
        self.model_id = {
            GPT3ResourceTypes.embeddings.value: kwargs.get("embeddings_model_id"),
            GPT3ResourceTypes.chat_completion.value: kwargs.get("chat_completion_model_id")
        }

    def get_headers(self):
        return {"api-key": f"Bearer {self.api_key}"}

    def get_resource_url(self, resource: Text):
        model_id = self.model_id[resource]
        resource_url = f"{self.resource_url}/{model_id}/{resource}?api-version={self.api_version}"
        return resource_url
