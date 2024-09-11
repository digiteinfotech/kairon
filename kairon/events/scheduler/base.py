from abc import ABC, abstractmethod
from typing import Text

from kairon.shared.data.constant import TASK_TYPE


class EventSchedulerBase(ABC):

    @property
    def name(self):
        return self.__class__.__name__

    @abstractmethod
    def add_job(self, event_id: Text, task_type: TASK_TYPE, cron_exp: Text, event_class: Text, body: dict):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def update_job(self, event_id: Text, task_type: TASK_TYPE, cron_exp: Text, event_class: Text, body: dict):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def list_jobs(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def get_job(self, event_id):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def delete_job(self, event_id):
        raise NotImplementedError("Provider not implemented")
