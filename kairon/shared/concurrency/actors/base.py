from abc import ABC

from pykka import ThreadingActor


class BaseActor(ThreadingActor, ABC):

    def execute(self, **kwargs):
        raise NotImplementedError("Provider not implemented!")
