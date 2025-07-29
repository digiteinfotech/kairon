
from kairon.shared.log_system.base import BaseLogHandler

class ActionLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        query = {"bot": self.bot, "trigger_info__trigger_id": ""}
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("bot")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        from_date = self.kwargs.pop("from_date", None)
        to_date = self.kwargs.pop("to_date", None)

        query = {
            "bot": self.bot,
            "trigger_info__trigger_id": ""
        }

        if from_date:
            query["timestamp__gte"] = from_date
        if to_date:
            query["timestamp__lte"] = to_date

        query.update(self.kwargs)

        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").exclude("bot")
        logs = json.loads(logs_cursor.to_json())
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

