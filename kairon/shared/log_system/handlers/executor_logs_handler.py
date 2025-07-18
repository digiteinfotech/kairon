import json
from kairon.shared.log_system.base import BaseLogHandler



class ExecutorLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from kairon.shared.log_system.executor import LogExecutor
        query = {"bot": self.bot}
        for field in ["event_class", "task_type"]:
            value = self.kwargs.get(field)
            if value:
                query[field] = value
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("_id")
        logs = json.loads(logs_cursor.to_json())
        count = LogExecutor.get_logs_count(self.doc_type, **query)
        return logs, count
