from abc import abstractmethod


class CatalogSyncBase:

    """Base class to create events"""

    @abstractmethod
    def validate(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def preprocess(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def execute(self, **kwargs):
        raise NotImplementedError("Provider not implemented")