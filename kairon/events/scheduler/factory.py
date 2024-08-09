from kairon import Utility
from kairon.events.scheduler.kscheduler import KScheduler
from kairon.exceptions import AppException


class SchedulerFactory:

    __implementations = {
        "kscheduler": KScheduler
    }

    @staticmethod
    def get_instance():
        scheduler_type = Utility.environment["events"]["scheduler"]["type"]
        if scheduler_type not in SchedulerFactory.__implementations.keys():
            raise AppException(f"scheduler type '{scheduler_type}' not implemented!")
        return SchedulerFactory.__implementations[scheduler_type]()
