from abc import ABC, abstractmethod
from typing import Dict, Text


class WhatsappBusinessServiceProviderBase(ABC):

    @abstractmethod
    def get_account(self, account_id: Text):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def post_process(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def save_channel_config(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def add_template(self, data: Dict, bot: Text, user: Text):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def edit_template(self, data: Dict, template_id: str):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def delete_template(self, template_name: str):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def get_template(self, template_id: Text):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def list_templates(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def validate(self, **kwargs):
        raise NotImplementedError("Provider not implemented")
