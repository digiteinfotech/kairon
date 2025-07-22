from abc import ABC, abstractmethod


class BaseLogHandler(ABC):
    def __init__(self, doc_type, bot, start_idx, page_size, **kwargs):
        self.doc_type = doc_type
        self.bot = bot
        self.start_idx = start_idx
        self.page_size = page_size
        self.kwargs = kwargs

    @abstractmethod
    def get_logs_and_count(self):
        pass

