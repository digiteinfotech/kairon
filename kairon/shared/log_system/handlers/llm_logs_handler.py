from kairon.shared.log_system.base import BaseLogHandler

class LLMLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        query = {"metadata__bot": self.bot}
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        from_date = self.kwargs.pop("from_date", None)
        to_date = self.kwargs.pop("to_date", None)

        query = {"metadata__bot": self.bot}

        if from_date:
            query["start_time__gte"] = from_date
        if to_date:
            query["start_time__lte"] = to_date

        query.update(self.kwargs)

        logs_cursor = (
            self.doc_type.objects(**query)
            .order_by("-timestamp")
            .exclude("id")
        )
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count
