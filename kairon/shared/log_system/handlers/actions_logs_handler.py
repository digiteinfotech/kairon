from kairon.shared.log_system.base import BaseLogHandler


class ActionLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date, to_date = BaseLogHandler.get_default_dates(self.kwargs, "count")
        query = {
            "bot": self.bot,
            "timestamp__gte": from_date,
            "timestamp__lte": to_date,
            "trigger_info__trigger_id": "",
        }
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(
            self.page_size).exclude("bot")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        query = BaseLogHandler.get_default_dates(self.kwargs, "search")
        query["bot"] = self.bot
        query["trigger_info__trigger_id"] = ""
        if "downloads" in self.kwargs.keys():
            logs_cursor = self.doc_type.objects(**query).order_by("-timestamp")
        else:
            logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(
            self.page_size).exclude("bot")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count



