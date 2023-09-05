import os
import re

from mock import patch

import pytest
from apscheduler.jobstores.mongodb import MongoDBJobStore
from bson import ObjectId
from pymongo.results import UpdateResult, DeleteResult
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.shared.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"

with patch("pymongo.collection.Collection.create_index"):
    with patch.dict(os.environ, {"DATABASE_URL": "mongodb://local:27035"}):
        Utility.load_environment()
        from kairon.events.scheduler.kscheduler import KScheduler


class TestMessageBroadcastProcessor:

    def test_scheduler_attributes(self):
        bot = "test_bot"
        user = "test_user"
        scheduler = KScheduler()
        assert scheduler.name == "KScheduler"
        assert scheduler._KScheduler__scheduler._job_defaults == {'misfire_grace_time': 7200, 'coalesce': True,
                                                                  'max_instances': 1}
        scheduler_type = Utility.environment["events"]["scheduler"]["type"]
        mongostore = scheduler._KScheduler__scheduler._jobstores[scheduler_type]
        assert isinstance(mongostore, MongoDBJobStore)
        assert mongostore.collection.full_name == f'{Utility.environment["events"]["queue"]["name"]}.' \
                                                  f'{Utility.environment["events"]["scheduler"]["collection"]}'

    @patch("apscheduler.jobstores.mongodb.MongoDBJobStore.add_job", autospec=True)
    def test_add_schedule(self, mock_jobstore):
        bot = "test_bot"
        user = "test_user"
        event_id = ObjectId().__str__()
        cron_exp = "21 11 1 4 1"
        body = {"bot": bot, "user": user, "event_id": event_id}
        scheduler = KScheduler()

        with patch.dict(Utility.environment["events"]["executor"], {"type": "aws_lambda"}):
            scheduler.add_job(event_id, cron_exp, EventClass.message_broadcast.value, body, "Asia/Kolkata")

            assert mock_jobstore.call_args.args[1].args[0] == 'message_broadcast'
            mock_jobstore.call_args.args[1].args[1].pop("event_id")
            assert mock_jobstore.call_args.args[1].args[1] == {'bot': 'test_bot', 'user': 'test_user'}
            assert mock_jobstore.call_args.args[1].coalesce
            assert mock_jobstore.call_args.args[
                       1].func_ref == 'kairon.events.executors.lamda:LambdaExecutor.execute_task'
            assert mock_jobstore.call_args.args[1].id
            assert mock_jobstore.call_args.args[1].trigger
            assert mock_jobstore.call_args.args[1].trigger.timezone.zone == 'Asia/Kolkata'

    @patch("pymongo.collection.Collection.find")
    def test_list_jobs(self, mock_jobstore):
        bot = "test_bot"
        user = "test_user"
        pickled_jobs = {'_id': '6425c8a78bfce37a0bc6a962',
                        'job_state': b'\x80\x05\x95\xbf\x04\x00\x00\x00\x00\x00\x00}\x94(\x8c\x07version\x94K\x01\x8c\x02id\x94\x8c\x186425c8a78bfce37a0bc6a962\x94\x8c\x04func\x94\x8c9kairon.events.executors.lamda:LambdaExecutor.execute_task\x94\x8c\x07trigger\x94\x8c\x19apscheduler.triggers.cron\x94\x8c\x0bCronTrigger\x94\x93\x94)\x81\x94}\x94(h\x01K\x02\x8c\x08timezone\x94\x8c\x04pytz\x94\x8c\x02_p\x94\x93\x94(\x8c\x0cAsia/Kolkata\x94M\xbcRK\x00\x8c\x03LMT\x94t\x94R\x94\x8c\nstart_date\x94N\x8c\x08end_date\x94N\x8c\x06fields\x94]\x94(\x8c apscheduler.triggers.cron.fields\x94\x8c\tBaseField\x94\x93\x94)\x81\x94}\x94(\x8c\x04name\x94\x8c\x04year\x94\x8c\nis_default\x94\x88\x8c\x0bexpressions\x94]\x94\x8c%apscheduler.triggers.cron.expressions\x94\x8c\rAllExpression\x94\x93\x94)\x81\x94}\x94\x8c\x04step\x94Nsbaubh\x18\x8c\nMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x05month\x94h\x1f\x89h ]\x94h"\x8c\x0fRangeExpression\x94\x93\x94)\x81\x94}\x94(h\'N\x8c\x05first\x94K\x04\x8c\x04last\x94K\x04ubaubh\x18\x8c\x0fDayOfMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x03day\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x18\x8c\tWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x04week\x94h\x1f\x88h ]\x94h$)\x81\x94}\x94h\'Nsbaubh\x18\x8c\x0eDayOfWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x0bday_of_week\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x04hour\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x0bh3K\x0bubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06minute\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x15h3K\x15ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06second\x94h\x1f\x88h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x00h3K\x00ubaube\x8c\x06jitter\x94Nub\x8c\x08executor\x94\x8c\x07default\x94\x8c\x04args\x94\x8c\x1dkairon.events.executors.lamda\x94\x8c\x0eLambdaExecutor\x94\x93\x94)\x81\x94\x8c\x11message_broadcast\x94}\x94(\x8c\x03bot\x94\x8c\x08test_bot\x94\x8c\x04user\x94\x8c\ttest_user\x94\x8c\x08event_id\x94h\x03u\x87\x94\x8c\x06kwargs\x94}\x94h\x1d\x8c\x0cexecute_task\x94\x8c\x12misfire_grace_time\x94M \x1c\x8c\x08coalesce\x94\x88\x8c\rmax_instances\x94K\x01\x8c\rnext_run_time\x94\x8c\x08datetime\x94\x8c\x08datetime\x94\x93\x94C\n\x07\xe9\x04\x01\x0b\x15\x00\x00\x00\x00\x94h\x0f(h\x10MXMK\x00\x8c\x03IST\x94t\x94R\x94\x86\x94R\x94u.'}, {
                           '_id': '6425c9223603a1e5de0d218e',
                           'job_state': b'\x80\x05\x95\xbf\x04\x00\x00\x00\x00\x00\x00}\x94(\x8c\x07version\x94K\x01\x8c\x02id\x94\x8c\x186425c9223603a1e5de0d218e\x94\x8c\x04func\x94\x8c9kairon.events.executors.lamda:LambdaExecutor.execute_task\x94\x8c\x07trigger\x94\x8c\x19apscheduler.triggers.cron\x94\x8c\x0bCronTrigger\x94\x93\x94)\x81\x94}\x94(h\x01K\x02\x8c\x08timezone\x94\x8c\x04pytz\x94\x8c\x02_p\x94\x93\x94(\x8c\x0cAsia/Kolkata\x94M\xbcRK\x00\x8c\x03LMT\x94t\x94R\x94\x8c\nstart_date\x94N\x8c\x08end_date\x94N\x8c\x06fields\x94]\x94(\x8c apscheduler.triggers.cron.fields\x94\x8c\tBaseField\x94\x93\x94)\x81\x94}\x94(\x8c\x04name\x94\x8c\x04year\x94\x8c\nis_default\x94\x88\x8c\x0bexpressions\x94]\x94\x8c%apscheduler.triggers.cron.expressions\x94\x8c\rAllExpression\x94\x93\x94)\x81\x94}\x94\x8c\x04step\x94Nsbaubh\x18\x8c\nMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x05month\x94h\x1f\x89h ]\x94h"\x8c\x0fRangeExpression\x94\x93\x94)\x81\x94}\x94(h\'N\x8c\x05first\x94K\x04\x8c\x04last\x94K\x04ubaubh\x18\x8c\x0fDayOfMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x03day\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x18\x8c\tWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x04week\x94h\x1f\x88h ]\x94h$)\x81\x94}\x94h\'Nsbaubh\x18\x8c\x0eDayOfWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x0bday_of_week\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x04hour\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x0bh3K\x0bubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06minute\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x15h3K\x15ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06second\x94h\x1f\x88h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x00h3K\x00ubaube\x8c\x06jitter\x94Nub\x8c\x08executor\x94\x8c\x07default\x94\x8c\x04args\x94\x8c\x1dkairon.events.executors.lamda\x94\x8c\x0eLambdaExecutor\x94\x93\x94)\x81\x94\x8c\x11message_broadcast\x94}\x94(\x8c\x03bot\x94\x8c\x08test_bot\x94\x8c\x04user\x94\x8c\ttest_user\x94\x8c\x08event_id\x94h\x03u\x87\x94\x8c\x06kwargs\x94}\x94h\x1d\x8c\x0cexecute_task\x94\x8c\x12misfire_grace_time\x94M \x1c\x8c\x08coalesce\x94\x88\x8c\rmax_instances\x94K\x01\x8c\rnext_run_time\x94\x8c\x08datetime\x94\x8c\x08datetime\x94\x93\x94C\n\x07\xe9\x04\x01\x0b\x15\x00\x00\x00\x00\x94h\x0f(h\x10MXMK\x00\x8c\x03IST\x94t\x94R\x94\x86\x94R\x94u.'},

        mock_jobstore.return_value = pickled_jobs
        scheduler = KScheduler()
        assert scheduler.list_jobs() == ['6425c8a78bfce37a0bc6a962', '6425c9223603a1e5de0d218e']

    @patch("pymongo.collection.Collection.find_one")
    def test_get_job(self, mock_find_job):
        bot = "test_bot"
        user = "test_user"
        scheduler = KScheduler()

        def __mock_mongo_get_job(*args, **kwargs):
            return {'_id': '6425ca191eaaf86e3a7b5e3f',
                    'job_state': b'\x80\x05\x95\xbf\x04\x00\x00\x00\x00\x00\x00}\x94(\x8c\x07version\x94K\x01\x8c\x02id\x94\x8c\x186425ca191eaaf86e3a7b5e3f\x94\x8c\x04func\x94\x8c9kairon.events.executors.lamda:LambdaExecutor.execute_task\x94\x8c\x07trigger\x94\x8c\x19apscheduler.triggers.cron\x94\x8c\x0bCronTrigger\x94\x93\x94)\x81\x94}\x94(h\x01K\x02\x8c\x08timezone\x94\x8c\x04pytz\x94\x8c\x02_p\x94\x93\x94(\x8c\x0cAsia/Kolkata\x94M\xbcRK\x00\x8c\x03LMT\x94t\x94R\x94\x8c\nstart_date\x94N\x8c\x08end_date\x94N\x8c\x06fields\x94]\x94(\x8c apscheduler.triggers.cron.fields\x94\x8c\tBaseField\x94\x93\x94)\x81\x94}\x94(\x8c\x04name\x94\x8c\x04year\x94\x8c\nis_default\x94\x88\x8c\x0bexpressions\x94]\x94\x8c%apscheduler.triggers.cron.expressions\x94\x8c\rAllExpression\x94\x93\x94)\x81\x94}\x94\x8c\x04step\x94Nsbaubh\x18\x8c\nMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x05month\x94h\x1f\x89h ]\x94h"\x8c\x0fRangeExpression\x94\x93\x94)\x81\x94}\x94(h\'N\x8c\x05first\x94K\x04\x8c\x04last\x94K\x04ubaubh\x18\x8c\x0fDayOfMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x03day\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x18\x8c\tWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x04week\x94h\x1f\x88h ]\x94h$)\x81\x94}\x94h\'Nsbaubh\x18\x8c\x0eDayOfWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x0bday_of_week\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x04hour\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x0bh3K\x0bubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06minute\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x15h3K\x15ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06second\x94h\x1f\x88h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x00h3K\x00ubaube\x8c\x06jitter\x94Nub\x8c\x08executor\x94\x8c\x07default\x94\x8c\x04args\x94\x8c\x1dkairon.events.executors.lamda\x94\x8c\x0eLambdaExecutor\x94\x93\x94)\x81\x94\x8c\x11message_broadcast\x94}\x94(\x8c\x03bot\x94\x8c\x08test_bot\x94\x8c\x04user\x94\x8c\ttest_user\x94\x8c\x08event_id\x94h\x03u\x87\x94\x8c\x06kwargs\x94}\x94h\x1d\x8c\x0cexecute_task\x94\x8c\x12misfire_grace_time\x94M \x1c\x8c\x08coalesce\x94\x88\x8c\rmax_instances\x94K\x01\x8c\rnext_run_time\x94\x8c\x08datetime\x94\x8c\x08datetime\x94\x93\x94C\n\x07\xe9\x04\x01\x0b\x15\x00\x00\x00\x00\x94h\x0f(h\x10MXMK\x00\x8c\x03IST\x94t\x94R\x94\x86\x94R\x94u.'}

        mock_find_job.return_value = __mock_mongo_get_job()
        job_info = scheduler.get_job('6425ca191eaaf86e3a7b5e3f')

        assert job_info.args[2] == {'bot': 'test_bot', 'user': 'test_user', 'event_id': '6425ca191eaaf86e3a7b5e3f'}
        assert job_info.coalesce
        assert job_info.func_ref == 'kairon.events.executors.lamda:LambdaExecutor.execute_task'
        assert job_info.id == '6425ca191eaaf86e3a7b5e3f'
        assert job_info.misfire_grace_time == 7200
        assert job_info.name == "execute_task"
        assert job_info.trigger

    @patch("pymongo.collection.Collection.find_one")
    def test_get_job_not_exists(self, mock_find_job):
        bot = "test_bot"
        user = "test_user"
        scheduler = KScheduler()
        mock_find_job.return_value = None
        with pytest.raises(AppException, match="Job not found!"):
            scheduler.get_job(ObjectId().__str__())

    def test_add_schedule_executor_not_configured(self, monkeypatch):
        bot = "test_bot"
        user = "test_user"
        event_id = ObjectId().__str__()
        cron_exp = "21 11 * * *"
        body = {"bot": bot, "user": user, "event_id": event_id}
        scheduler = KScheduler()
        monkeypatch.setitem(Utility.environment["events"]["executor"], "type", None)
        with pytest.raises(AppException, match=re.escape(
                "Executor type not configured in system.yaml. Valid types: ['aws_lambda', 'dramatiq', 'standalone']")):
            scheduler.add_job(event_id, cron_exp, EventClass.message_broadcast.value, body)

    @patch("pymongo.collection.Collection.find_one")
    @patch("pymongo.collection.Collection.update_one")
    def test_update_schedule(self, mock_mongo, mock_find_job):
        bot = "test_bot"
        user = "test_user"
        event_id = ObjectId().__str__()
        cron_exp = "21 11 1 4 1"
        body = {"bot": bot, "user": user, "event_id": event_id}
        scheduler = KScheduler()

        def __mock_mongo_get_job(*args, **kwargs):
            return {'_id': '6425ca191eaaf86e3a7b5e3f',
                    'job_state': b'\x80\x05\x95\xbf\x04\x00\x00\x00\x00\x00\x00}\x94(\x8c\x07version\x94K\x01\x8c\x02id\x94\x8c\x186425ca191eaaf86e3a7b5e3f\x94\x8c\x04func\x94\x8c9kairon.events.executors.lamda:LambdaExecutor.execute_task\x94\x8c\x07trigger\x94\x8c\x19apscheduler.triggers.cron\x94\x8c\x0bCronTrigger\x94\x93\x94)\x81\x94}\x94(h\x01K\x02\x8c\x08timezone\x94\x8c\x04pytz\x94\x8c\x02_p\x94\x93\x94(\x8c\x0cAsia/Kolkata\x94M\xbcRK\x00\x8c\x03LMT\x94t\x94R\x94\x8c\nstart_date\x94N\x8c\x08end_date\x94N\x8c\x06fields\x94]\x94(\x8c apscheduler.triggers.cron.fields\x94\x8c\tBaseField\x94\x93\x94)\x81\x94}\x94(\x8c\x04name\x94\x8c\x04year\x94\x8c\nis_default\x94\x88\x8c\x0bexpressions\x94]\x94\x8c%apscheduler.triggers.cron.expressions\x94\x8c\rAllExpression\x94\x93\x94)\x81\x94}\x94\x8c\x04step\x94Nsbaubh\x18\x8c\nMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x05month\x94h\x1f\x89h ]\x94h"\x8c\x0fRangeExpression\x94\x93\x94)\x81\x94}\x94(h\'N\x8c\x05first\x94K\x04\x8c\x04last\x94K\x04ubaubh\x18\x8c\x0fDayOfMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x03day\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x18\x8c\tWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x04week\x94h\x1f\x88h ]\x94h$)\x81\x94}\x94h\'Nsbaubh\x18\x8c\x0eDayOfWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x0bday_of_week\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x04hour\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x0bh3K\x0bubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06minute\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x15h3K\x15ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06second\x94h\x1f\x88h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x00h3K\x00ubaube\x8c\x06jitter\x94Nub\x8c\x08executor\x94\x8c\x07default\x94\x8c\x04args\x94\x8c\x1dkairon.events.executors.lamda\x94\x8c\x0eLambdaExecutor\x94\x93\x94)\x81\x94\x8c\x11message_broadcast\x94}\x94(\x8c\x03bot\x94\x8c\x08test_bot\x94\x8c\x04user\x94\x8c\ttest_user\x94\x8c\x08event_id\x94h\x03u\x87\x94\x8c\x06kwargs\x94}\x94h\x1d\x8c\x0cexecute_task\x94\x8c\x12misfire_grace_time\x94M \x1c\x8c\x08coalesce\x94\x88\x8c\rmax_instances\x94K\x01\x8c\rnext_run_time\x94\x8c\x08datetime\x94\x8c\x08datetime\x94\x93\x94C\n\x07\xe9\x04\x01\x0b\x15\x00\x00\x00\x00\x94h\x0f(h\x10MXMK\x00\x8c\x03IST\x94t\x94R\x94\x86\x94R\x94u.'}

        with patch.dict(Utility.environment["events"]["executor"], {"type": "aws_lambda"}):
            mock_find_job.return_value = __mock_mongo_get_job()
            mongo_result = UpdateResult({"n": 1}, True)
            mock_mongo.return_value = mongo_result
            scheduler.update_job(event_id, cron_exp, EventClass.message_broadcast.value, body)

    @patch("pymongo.collection.Collection.find_one")
    def test_update_schedule_not_found(self, mock_find_job):
        bot = "test_bot"
        user = "test_user"
        event_id = "6425ca191eaaf86e3a7b5e3f"
        cron_exp = "21 11 1 4 1"
        body = {"bot": bot, "user": user, "event_id": event_id}
        scheduler = KScheduler()

        mock_find_job.return_value = {}
        with patch.dict(Utility.environment["events"]["executor"], {"type": "aws_lambda"}):
            with pytest.raises(AppException, match='No job by the id of 6425ca191eaaf86e3a7b5e3f was found'):
                scheduler.update_job(event_id, cron_exp, EventClass.message_broadcast.value, body)

    @patch("pymongo.collection.Collection.find_one")
    @patch("pymongo.collection.Collection.update_one")
    def test_update_failure(self, mock_mongo, mock_find_job):
        bot = "test_bot"
        user = "test_user"
        event_id = "6425ca191eaaf86e3a7b5e3f"
        cron_exp = "21 11 1 4 1"
        body = {"bot": bot, "user": user, "event_id": event_id}
        scheduler = KScheduler()

        def __mock_mongo_get_job(*args, **kwargs):
            return {'_id': event_id,
                    'job_state': b'\x80\x05\x95\xbf\x04\x00\x00\x00\x00\x00\x00}\x94(\x8c\x07version\x94K\x01\x8c\x02id\x94\x8c\x186425ca191eaaf86e3a7b5e3f\x94\x8c\x04func\x94\x8c9kairon.events.executors.lamda:LambdaExecutor.execute_task\x94\x8c\x07trigger\x94\x8c\x19apscheduler.triggers.cron\x94\x8c\x0bCronTrigger\x94\x93\x94)\x81\x94}\x94(h\x01K\x02\x8c\x08timezone\x94\x8c\x04pytz\x94\x8c\x02_p\x94\x93\x94(\x8c\x0cAsia/Kolkata\x94M\xbcRK\x00\x8c\x03LMT\x94t\x94R\x94\x8c\nstart_date\x94N\x8c\x08end_date\x94N\x8c\x06fields\x94]\x94(\x8c apscheduler.triggers.cron.fields\x94\x8c\tBaseField\x94\x93\x94)\x81\x94}\x94(\x8c\x04name\x94\x8c\x04year\x94\x8c\nis_default\x94\x88\x8c\x0bexpressions\x94]\x94\x8c%apscheduler.triggers.cron.expressions\x94\x8c\rAllExpression\x94\x93\x94)\x81\x94}\x94\x8c\x04step\x94Nsbaubh\x18\x8c\nMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x05month\x94h\x1f\x89h ]\x94h"\x8c\x0fRangeExpression\x94\x93\x94)\x81\x94}\x94(h\'N\x8c\x05first\x94K\x04\x8c\x04last\x94K\x04ubaubh\x18\x8c\x0fDayOfMonthField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x03day\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x18\x8c\tWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x04week\x94h\x1f\x88h ]\x94h$)\x81\x94}\x94h\'Nsbaubh\x18\x8c\x0eDayOfWeekField\x94\x93\x94)\x81\x94}\x94(h\x1d\x8c\x0bday_of_week\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x01h3K\x01ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x04hour\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x0bh3K\x0bubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06minute\x94h\x1f\x89h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x15h3K\x15ubaubh\x1a)\x81\x94}\x94(h\x1d\x8c\x06second\x94h\x1f\x88h ]\x94h/)\x81\x94}\x94(h\'Nh2K\x00h3K\x00ubaube\x8c\x06jitter\x94Nub\x8c\x08executor\x94\x8c\x07default\x94\x8c\x04args\x94\x8c\x1dkairon.events.executors.lamda\x94\x8c\x0eLambdaExecutor\x94\x93\x94)\x81\x94\x8c\x11message_broadcast\x94}\x94(\x8c\x03bot\x94\x8c\x08test_bot\x94\x8c\x04user\x94\x8c\ttest_user\x94\x8c\x08event_id\x94h\x03u\x87\x94\x8c\x06kwargs\x94}\x94h\x1d\x8c\x0cexecute_task\x94\x8c\x12misfire_grace_time\x94M \x1c\x8c\x08coalesce\x94\x88\x8c\rmax_instances\x94K\x01\x8c\rnext_run_time\x94\x8c\x08datetime\x94\x8c\x08datetime\x94\x93\x94C\n\x07\xe9\x04\x01\x0b\x15\x00\x00\x00\x00\x94h\x0f(h\x10MXMK\x00\x8c\x03IST\x94t\x94R\x94\x86\x94R\x94u.'}

        with patch.dict(Utility.environment["events"]["executor"], {"type": "aws_lambda"}):
            mock_find_job.return_value = __mock_mongo_get_job()
            mongo_result = UpdateResult({"n": 0}, True)
            mock_mongo.return_value = mongo_result

            with pytest.raises(AppException, match='No job by the id of 6425ca191eaaf86e3a7b5e3f was found'):
                scheduler.update_job(event_id, cron_exp, EventClass.message_broadcast.value, body)

    @patch("pymongo.collection.Collection.delete_one")
    def test_delete_schedule(self, mock_mongo):
        bot = "test_bot"
        user = "test_user"
        event_id = ObjectId().__str__()
        scheduler = KScheduler()
        mongo_result = DeleteResult({"n": 1}, True)
        mock_mongo.return_value = mongo_result
        scheduler.delete_job(event_id)

    @patch("pymongo.collection.Collection.delete_one")
    def test_delete_schedule_not_exists(self, mock_mongo):
        bot = "test_bot"
        user = "test_user"
        event_id = ObjectId().__str__()
        scheduler = KScheduler()
        mongo_result = DeleteResult({"n": 0}, True)
        mock_mongo.return_value = mongo_result
        with pytest.raises(AppException, match=f'No job by the id of {event_id} was found'):
            scheduler.delete_job(event_id)

    @patch("pymongo.collection.Collection.find")
    def test_list_schedules_none(self, mock_jobstore):
        bot = "test_bot"
        user = "test_user"
        scheduler = KScheduler()
        mock_jobstore.return_value = []
        assert scheduler.list_jobs() == []
