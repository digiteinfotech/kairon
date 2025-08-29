from ..base import BaseLogHandler


class AgentHandoffLogHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date, to_date = BaseLogHandler.get_default_dates(self.kwargs,"logs_and_count")
        query = {
            "account": self.kwargs.get("bot_account", 0),
            "bot": self.bot,
            "metric_type": "agent_handoff",
            "timestamp__gte": from_date,
            "timestamp__lte": to_date
        }
        logs_cursor = self.doc_type.objects(**query).order_by("-timestamp").skip(self.start_idx).limit(self.page_size).exclude("id")
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        self.kwargs["stamp"]="timestamp"
        query= BaseLogHandler.get_default_dates(self.kwargs, "logs_for_search")
        query["bot"]= self.bot,
        query["metric_type"]= "agent_handoff"
        logs_cursor = (
            self.doc_type.objects(**query)
            .order_by("-timestamp")
            .skip(self.start_idx)
            .limit(self.page_size)
            .exclude("id")
        )
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count