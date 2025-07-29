from ..base import BaseLogHandler
from datetime import datetime, timedelta

class AuditLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date = self.kwargs.get("from_date") or datetime.utcnow().date()
        to_date = self.kwargs.get("to_date") or from_date + timedelta(days=1)
        to_date += timedelta(days=1)
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
