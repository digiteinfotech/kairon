from abc import ABC, abstractmethod
from typing import Dict


class WhatsappBusinessServiceProviderBase(ABC):

    @abstractmethod
    def get_account(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def post_process(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def save_channel_config(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def add_template(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def edit_template(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def delete_template(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def get_template(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def list_templates(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def validate(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def validate_template_request(self, data: Dict):
        raise NotImplementedError("Provider not implemented")

    @staticmethod
    def fetch_media_ids(bot: str):
        raise NotImplementedError("Provider not implemented")

    @staticmethod
    def fetch_broadcast_media_ids(bot: str):
        raise NotImplementedError("Provider not implemented")

    def normalize_raw_template(self, raw_template):
        raise NotImplementedError("Provider not implemented")

    def get_template_params_for_broadcast(self, raw_template, template_config, recipients, default_params):
        raise NotImplementedError("Provider not implemented")

    def get_broadcast_namespace_and_language(self, raw_template, namespace, lang):
        raise NotImplementedError("Provider not implemented")
