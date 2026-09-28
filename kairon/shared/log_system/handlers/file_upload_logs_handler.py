from kairon.shared.log_system.base import BaseLogHandler
from datetime import datetime, timedelta


class FileUploadHandler(BaseLogHandler):

    def get_logs_and_count(self):
        query = {"bot": self.bot}
        query["start_timestamp__gte"] = datetime.utcnow() - timedelta(days=30)
        sort_field = "-timestamp" if "timestamp" in self.doc_type._fields else "-start_timestamp"
        logs_cursor = self.doc_type.objects(**query).order_by(sort_field).skip(self.start_idx).limit(
            self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count

    def get_logs_for_search_query(self):
        self.kwargs["stamp"] = "start_timestamp"
        query = BaseLogHandler.get_default_dates(self.kwargs, "search")
        query["bot"] = self.bot
        sort_field = "-start_timestamp"
        logs_cursor = (
            self.doc_type.objects(**query)
            .order_by(sort_field)
            .skip(self.start_idx)
            .limit(self.page_size)
            .exclude("id")
        )
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count