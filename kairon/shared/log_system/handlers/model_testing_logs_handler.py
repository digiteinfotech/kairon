
from ..base import BaseLogHandler

from ...test.data_objects import ModelTestingLogs

class ModelTestingHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from_date, to_date = BaseLogHandler.get_default_dates(self.kwargs, "count")
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
        self.kwargs["stamp"] = "start_timestamp"
        query = BaseLogHandler.get_default_dates(self.kwargs, "search")

        from_date = query.pop("start_timestamp__gte", None)
        to_date = query.pop("start_timestamp__lte", None)

        match_stage = {"bot": self.bot}
        match_stage["$and"] = [
            {"start_timestamp": {"$exists": True}},
            {"start_timestamp": {"$gte": from_date, "$lte": to_date}},
        ]
        for k, v in list(query.items()):
            if v is None:
                continue
            if k == "is_augmented":
                match_stage["is_augmented"] = v.lower() == "true"
            else:
                match_stage[k] = v
        logs = list(ModelTestingLogs.objects(bot=self.bot).aggregate([
            {"$set": {"data.type": "$type"}},
            {'$group': {
                '_id': '$reference_id',
                'bot': {'$first': '$bot'},
                'user': {'$first': '$user'},
                'status': {'$first': '$status'},
                'event_status': {'$first': '$event_status'},
                'data': {'$push': '$data'},
                'exception': {'$first': '$exception'},
                'start_timestamp': {'$first': '$start_timestamp'},
                'end_timestamp': {'$first': '$end_timestamp'},
                'is_augmented': {'$first': '$is_augmented'}
            }},
            {"$match": match_stage},
            {'$project': {
                '_id': 0,
                'reference_id': '$_id',
                'data': {
                    '$filter': {
                        'input': '$data',
                        'as': 'data',
                        'cond': {'$ne': ['$$data.type', 'common']}
                    }
                },
                'status': 1,
                'event_status': 1,
                'exception': 1,
                'start_timestamp': 1,
                'end_timestamp': 1,
                'is_augmented': 1
            }},

            {"$sort": {"start_timestamp": -1}}
        ]))[self.start_idx:self.start_idx + self.page_size]

        count_pipeline = [
            {"$match": match_stage},
            {"$count": "total"}
        ]
        count_result = list(ModelTestingLogs._get_collection().aggregate(count_pipeline))
        count = count_result[0]["total"] if count_result else 0
        return logs, count
