import abc


class Verification(abc.ABC):
    @abc.abstractmethod
    def verify(self, value: str, *args, **kwargs) -> bool:
        pass
