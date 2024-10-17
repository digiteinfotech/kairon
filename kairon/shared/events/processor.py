from kairon.shared.events.data_objects import ExecutorLogs


class ExecutorProcessor:

    @staticmethod
    def get_executor_logs(bot: str, start_idx: int = 0, page_size: int = 10, **kwargs):
        """
        Get all executor logs data .
        @param bot: bot id.
        @param start_idx: start index
        @param page_size: page size
        @return: list of logs.
        """
        event_class = kwargs.get("event_class")
        task_type = kwargs.get("task_type")
        query = {"bot": bot}
        if event_class:
            query.update({"event_class": event_class})
        if task_type:
            query.update({"task_type": task_type})
        for log in ExecutorLogs.objects(**query).order_by("-timestamp").skip(start_idx).limit(page_size):
            executor_logs = log.to_mongo().to_dict()
            executor_logs.pop('_id')
            yield executor_logs

    @staticmethod
    def get_row_count(bot: str, **kwargs):
        """
        Gets the count of rows in a ExecutorLogs for a particular bot.
        :param bot: bot id
        :return: Count of rows
        """
        event_class = kwargs.get("event_class")
        task_type = kwargs.get("task_type")
        query = {"bot": bot}
        if event_class:
            query.update({"event_class": event_class})
        if task_type:
            query.update({"task_type": task_type})
        return ExecutorLogs.objects(**query).count()
