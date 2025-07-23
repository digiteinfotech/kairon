import json

from kairon.shared.log_system.base import BaseLogHandler

class ActionLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        query = {"bot": self.bot, "trigger_info__trigger_id": ""}
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("bot")
        logs = json.loads(logs_cursor.to_json())
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count
