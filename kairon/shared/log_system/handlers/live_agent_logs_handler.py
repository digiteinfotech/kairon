from ..base import BaseLogHandler
from datetime import datetime
import calendar
import json


class AgentHandoffLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from kairon.shared.log_system.executor import LogExecutor
        from_date = self.kwargs.get("from_date") or datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        to_date = self.kwargs.get("to_date") or datetime.utcnow().replace(
            day=calendar.monthrange(datetime.utcnow().year, datetime.utcnow().month)[1]
        )
        query = {
            "account": self.kwargs.get("bot_account", 0),
            "bot": self.bot,
            "metric_type": "agent_handoff",
            "timestamp__gte": from_date,
            "timestamp__lte": to_date
        }
        logs_json = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id").to_json()
        count = LogExecutor.get_logs_count(self.doc_type, **query)
        return json.loads(logs_json), count
