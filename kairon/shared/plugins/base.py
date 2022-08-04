from abc import abstractmethod


class BasePlugin:

    @abstractmethod
    def execute(self, **kwargs):
        pass
