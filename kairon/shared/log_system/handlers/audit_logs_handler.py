from ..base import BaseLogHandler
from datetime import datetime, timedelta
import calendar

class AuditLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        now = datetime.utcnow()
        from_date = self.kwargs.get("from_date") or now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = calendar.monthrange(now.year, now.month)[1]
        to_date = self.kwargs.get("to_date") or now.replace(
            day=last_day, hour=23, minute=59, second=59, microsecond=999999)

        query = {
            "attributes__key": "bot",
            "attributes__value": self.bot,
            "timestamp__gte": from_date,
            "timestamp__lte": to_date
        }
        logs_json = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_json)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        from_date = self.kwargs.pop("from_date",None)
        to_date = self.kwargs.pop("to_date",None)
        to_date += timedelta(days=1)
        query = {
            "attributes__key": "bot",
            "attributes__value": self.bot,
            "timestamp__gte": from_date,
            "timestamp__lte": to_date
        }
        query.update(self.kwargs)
        logs_cursor = (self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id"))
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count