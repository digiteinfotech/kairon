from kairon.shared.log_system.base import BaseLogHandler

class DefaultLogHandler(BaseLogHandler):

    def get_logs_and_count(self):
        query = {"bot": self.bot}
        sort_field = "-timestamp" if "timestamp" in self.doc_type._fields else "-start_timestamp"
        logs_cursor = self.doc_type.objects(**query).order_by(sort_field).skip(self.start_idx).limit(
            self.page_size).exclude("bot", "user", "id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count