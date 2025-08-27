from kairon.shared.log_system.base import BaseLogHandler
from datetime import timedelta


class CallbackLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date, to_date = BaseLogHandler.get_default_dates(self.kwargs)
        query = {
            "bot": self.bot,
            "timestamp__gte": from_date,
            "timestamp__lte": to_date
        }
        for field in ["name", "sender_id", "channel", "identifier"]:
            value = self.kwargs.get(field)
            if value:
                query["callback_name" if field == "name" else field] = value
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        from_date = self.kwargs.pop("from_date", None)
        to_date = self.kwargs.pop("to_date", None)
        query = {"bot": self.bot}
        if from_date:
            query["timestamp__gte"] = from_date
        if to_date:
            query["timestamp__lte"] = to_date + timedelta(days=1)
        query.update(self.kwargs)

        logs_cursor = (self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id"))
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count

