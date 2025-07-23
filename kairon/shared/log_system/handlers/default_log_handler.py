import json

from kairon.shared.log_system.base import BaseLogHandler

class DefaultLogHandler(BaseLogHandler):

    def get_logs_and_count(self):
        query = {"bot": self.bot}
        sort_field = "-timestamp" if "timestamp" in self.doc_type._fields else "-start_timestamp"
        logs_cursor = self.doc_type.objects(**query).order_by(sort_field).skip(self.start_idx).limit(
            self.page_size).exclude("bot", "user", "id")
        logs = json.loads(logs_cursor.to_json())
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count