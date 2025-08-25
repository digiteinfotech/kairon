
from kairon.shared.log_system.base import BaseLogHandler
from datetime import datetime,timedelta
import calendar

class ActionLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date = self.kwargs.get("from_date") or datetime.utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        to_date = self.kwargs.get("to_date") or from_date.replace(
            day=calendar.monthrange(from_date.year, from_date.month)[1],
            hour=23, minute=59, second=59, microsecond=999999
        )
        query = {
            "bot": self.bot,
            "timestamp__gte": from_date,
            "timestamp__lte": to_date
        }


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
            query["timestamp__lte"] = to_date + timedelta(days=1)

        query.update(self.kwargs)

        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count

