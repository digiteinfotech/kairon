
from kairon.shared.log_system.base import BaseLogHandler

class ActionLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        query = {"bot": self.bot, "trigger_info__trigger_id": ""}
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("bot")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count
