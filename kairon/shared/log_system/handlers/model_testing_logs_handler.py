from ..base import BaseLogHandler

from ...test.data_objects import ModelTestingLogs


class ModelTestingHandler(BaseLogHandler):
    def get_logs_and_count(self):
        from kairon.shared.log_system.executor import LogExecutor

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
        query={"bot": self.bot,
               "type": "common"}
        count = LogExecutor.get_logs_count(self.doc_type, **query)
        return logs, count
