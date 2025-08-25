from ..base import BaseLogHandler

from ...test.data_objects import ModelTestingLogs
from datetime import datetime,timedelta
import calendar

class ModelTestingHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date = self.kwargs.get("from_date") or datetime.utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        to_date = self.kwargs.get("to_date") or from_date.replace(
            day=calendar.monthrange(from_date.year, from_date.month)[1],
            hour=23, minute=59, second=59, microsecond=999999
        )


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
        from_date = self.kwargs.pop("from_date", None)
        to_date = self.kwargs.pop("to_date", None)

        query = {"bot": self.bot}

        if from_date:
            query["start_timestamp__gte"] = from_date
        if to_date:
            query["start_timestamp__lte"] = to_date + timedelta(days=1)

        query.update(self.kwargs)

        logs_cursor = (self.doc_type.objects(**query).order_by("-start_timestamp").skip(self.start_idx).limit(self.page_size).exclude("id"))
        logs = BaseLogHandler.convert_logs_cursor_to_dict(logs_cursor)
        count = self.get_logs_count(self.doc_type,  **query)
        return logs, count
