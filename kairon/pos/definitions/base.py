from abc import abstractmethod, ABC


class POSBase(ABC):

    """Base class for POS"""

    @abstractmethod
    def onboarding(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def authenticate(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def products_list(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def orders_list(self, **kwargs):
        raise NotImplementedError("Provider not implemented")