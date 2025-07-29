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

    def get_logs_for_search_query(self):
        from_date = self.kwargs.pop("from_date", datetime.utcnow().date())
        to_date = self.kwargs.pop("to_date", from_date + timedelta(days=1))
        to_date += timedelta(days=1)

        query = {
            "attributes__key": "bot",
            "attributes__value": self.bot,
            "timestamp__gte": from_date,
            "timestamp__lte": to_date
        }

        query.update(self.kwargs)

        logs_cursor = (
            self.doc_type.objects(**query)
            .order_by("-timestamp")
            .exclude("id")
        )
        logs = json.loads(logs_cursor.to_json())
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count
