from abc import abstractmethod


class UploadHandlerBase:

    """Base class to create events"""

    @abstractmethod
    def validate(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def execute(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def create_payload(self, **kwargs):
        raise NotImplementedError("Provider not implemented")