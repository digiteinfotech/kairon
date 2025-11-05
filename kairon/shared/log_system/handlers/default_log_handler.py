
from kairon.shared.log_system.base import BaseLogHandler
from datetime import datetime


class DefaultLogHandler(BaseLogHandler):

    def get_logs_and_count(self):
        query = {"bot": self.bot}
        sort_field = "-timestamp" if "timestamp" in self.doc_type._fields else "-start_timestamp"
        logs_cursor = self.doc_type.objects(**query).order_by(sort_field).skip(self.start_idx).limit(
            self.page_size).exclude("bot", "id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        
        return logs, count

    def get_logs_for_search_query(self):
        if "timestamp" in self.doc_type._fields:
            sort_field = "-timestamp"
        else:
            sort_field = "-start_timestamp"
            self.kwargs["stamp"] = "start_timestamp"
        query = BaseLogHandler.get_default_dates(self.kwargs, "search")
        query["bot"] = self.bot

        logs_cursor = (
            self.doc_type.objects(**query)
            .order_by(sort_field)
            .skip(self.start_idx)
            .limit(self.page_size)
            .exclude("bot", "user", "id")
        )

        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query_for_unix_time(self):
        self.kwargs["stamp"] = "timestamp"
        query = BaseLogHandler.get_default_dates(self.kwargs, "search")
        query["bot"] = self.bot

        def to_unix_timestamp(dt: datetime):
            return int(dt.timestamp())

        query["timestamp__gte"] = to_unix_timestamp(query["timestamp__gte"])
        query["timestamp__lte"] = to_unix_timestamp(query["timestamp__lte"])
        sort_field = "-timestamp"
        logs_cursor = (
            self.doc_type.objects(**query)
            .order_by(sort_field)
            .skip(self.start_idx)
            .limit(self.page_size)
            .exclude("bot", "user", "id")
        )

        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count