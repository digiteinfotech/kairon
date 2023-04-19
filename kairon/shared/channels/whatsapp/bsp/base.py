from abc import ABC, abstractmethod


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
    def get_template(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def list_templates(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def validate(self, **kwargs):
        raise NotImplementedError("Provider not implemented")
