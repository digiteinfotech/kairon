from ..base import BaseLogHandler

from ...test.data_objects import ModelTestingLogs

class ModelTestingHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date,to_date=BaseLogHandler.get_default_dates(self.kwargs,"logs_and_count")
        logs = list(ModelTestingLogs.objects(bot=self.bot).aggregate([
            {"$set": {"data.type": "$type"}},
            {'$group': {'_id': '$reference_id', 'bot': {'$first': '$bot'}, 'user': {'$first': '$user'},
                        'status': {'$first': '$status'},
                        'event_status': {'$first': '$event_status'}, 'data': {'$push': '$data'},
                        'exception': {'$first': '$exception'},
                        'start_timestamp': {'$first': '$start_timestamp'},
                        'end_timestamp': {'$first': '$end_timestamp'},
                        'is_augmented': {'$first': '$is_augmented'}}},
            {'$project': {
                '_id': 0, 'reference_id': '$_id',
                'data': {'$filter': {'input': '$data', 'as': 'data', 'cond': {'$ne': ['$$data.type', 'common']}}},
                'status': 1, 'event_status': 1, 'exception': 1, 'start_timestamp': 1, 'end_timestamp': 1,
                'is_augmented': 1
            }},
            {"$sort": {"start_timestamp": -1}}]))[self.start_idx:self.start_idx + self.page_size]

        query = {
            "bot": self.bot,
            "type": "common",
            "start_timestamp__gte": from_date,
            "start_timestamp__lte": to_date
        }
        count = self.get_logs_count(self.doc_type, **query)
        return logs, count

    def get_logs_for_search_query(self):
        self.kwargs["stamp"]="start_timestamp"
        query = BaseLogHandler.get_default_dates(self.kwargs, "logs_for_search")
        is_augmented = self.kwargs.pop("is_augmented",None)
        query["bot"] = self.bot
        if is_augmented and is_augmented.lower() in ("true", "false"):
            query["is_augmented"] = is_augmented.lower() == "true"
        query.update(self.kwargs)
        logs_cursor = (self.doc_type.objects(**query).order_by("-start_timestamp").skip(self.start_idx).limit(self.page_size).exclude("id"))
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count