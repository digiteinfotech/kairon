from kairon.shared.log_system.base import BaseLogHandler
from datetime import timedelta

class LLMLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date, to_date = BaseLogHandler.get_default_dates(self.kwargs,"logs_and_count")
        query = {"metadata__bot": self.bot,
                 "start_time__gte": from_date,
                 "start_time__lte": to_date}

        logs_cursor = self.doc_type.objects(**query).order_by("-start_time").skip(self.start_idx).limit(self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        self.kwargs["stamp"]="start_time"
        query= BaseLogHandler.get_default_dates(self.kwargs, "logs_for_search")
        user = query.pop("user", None)
        invocation = query.pop("invocation", None)
        query["metadata__bot"] = self.bot

        if user:
            query["metadata__user"] = user
        if invocation:
            query["metadata__invocation"] = invocation

        logs_cursor = (self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id"))
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count