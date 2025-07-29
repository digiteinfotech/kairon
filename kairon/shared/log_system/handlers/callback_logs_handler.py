from kairon.shared.log_system.base import BaseLogHandler


class CallbackLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        query = {"bot": self.bot}
        for field in ["name", "sender_id", "channel", "identifier"]:
            value = self.kwargs.get(field)
            if value:
                query["callback_name" if field == "name" else field] = value
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count
