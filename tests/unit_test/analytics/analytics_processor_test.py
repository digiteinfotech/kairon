import os
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from mongoengine import connect, disconnect

from kairon import Utility
from kairon.exceptions import AppException
from fastapi import HTTPException

from kairon.shared.actions.data_objects import (
    AnalyticsPipelineConfig,
    SchedulerConfiguration,
)
from kairon.shared.analytics.analytics_pipeline_processor import AnalyticsPipelineProcessor
from kairon.shared.callback.data_objects import CallbackConfig

@pytest.mark.usefixtures("setup")
class TestAnalyticsPipelineProcessor:

    @pytest.fixture(autouse=True, scope="class")
    def setup(self, request):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_add_scheduled_task(self):
        data = {
            "pipeline_name": "daily-report",
            "callback_name": "cb1",
            "scheduler_config": {"expression_type": "cron", "schedule": "30 20 * * *", "timezone":"Asia/Kolkata"},
            "status": True,
        }

        event_id = AnalyticsPipelineProcessor.add_scheduled_task("bot1", "user1", data)
        assert event_id is not None

        saved = AnalyticsPipelineConfig.objects().first()
        assert saved.pipeline_name == "daily-report"
        assert saved.bot == "bot1"

    def test_add_scheduled_task_duplicate_name(self):
        data = {
            "pipeline_name": "dup-name",
            "callback_name": "cb1",
            "scheduler_config": {"expression_type": "cron", "schedule": "30 20 * * *", "timezone": "Asia/Kolkata"},
            "status": True,
        }
        AnalyticsPipelineProcessor.add_scheduled_task("bot1", "user1", data)

        with pytest.raises(AppException):
            AnalyticsPipelineProcessor.add_scheduled_task("bot1", "user1", data)

    def test_delete_task_permanent(self):
        obj = AnalyticsPipelineConfig(
            pipeline_name="p1",
            bot="b1",
            user="u1",
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="30 20 * * *", timezone = "Asia/Kolkata")
        ).save()

        AnalyticsPipelineProcessor.delete_task(str(obj.id), "b1", delete_permanently=True)
        assert AnalyticsPipelineConfig.objects().count() == 2
        assert AnalyticsPipelineConfig.objects(id=str(obj.id)).count() == 0

    def test_delete_task_soft(self):
        obj = AnalyticsPipelineConfig(
            pipeline_name="p1",
            bot="b1",
            user="u1",
            status=True,
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="30 20 * * *",  timezone = "Asia/Kolkata")
        ).save()

        AnalyticsPipelineProcessor.delete_task(str(obj.id), "b1", delete_permanently=False)
        updated = AnalyticsPipelineConfig.objects(id = str(obj.id),).first()
        assert updated.status is False

    def test_delete_task_not_found(self):
        with pytest.raises(AppException):
            AnalyticsPipelineProcessor.delete_task("69255e0feddf7785bcc0831b", "b1")

    def test_retrieve_config(self):
        obj = AnalyticsPipelineConfig(
            pipeline_name="p4",
            bot="b1",
            user="u1",
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="30 20 * * *", timezone = "Asia/Kolkata")
        ).save()

        data = AnalyticsPipelineProcessor.retrieve_config(str(obj.id), "b1")
        assert data["_id"] == str(obj.id)
        assert data["pipeline_name"] == "p4"

    def test_retrieve_config_not_found(self):
        with pytest.raises(AppException):
            AnalyticsPipelineProcessor.retrieve_config("69255e0feddf7785bcc0831b", "bot")

    def test_get_all_analytics_pipelines(self):
        AnalyticsPipelineConfig(
            pipeline_name="p3",
            bot="b1",
            user="u1",
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="30 20 * * *",
                                                    timezone="Asia/Kolkata")
        ).save()
        AnalyticsPipelineConfig(
            pipeline_name="p2",
            bot="b1",
            user="u1",
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="30 20 * * *", timezone = "Asia/Kolkata")
        ).save()

        result = AnalyticsPipelineProcessor.get_all_analytics_pipelines("b1")
        assert len(result) >= 2
        assert "_id" in result[0]

    def test_delete_analytics_pipeline(self):
        obj = AnalyticsPipelineConfig(
            pipeline_name="test_pipeline",
            bot="b1",
            user = "u1",
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="30 20 * * *", timezone= "Asia/Kolkata")
        ).save()

        result = AnalyticsPipelineProcessor.delete_analytics_pipeline("b1", str(obj.id))
        assert result is True

    def test_delete_analytics_pipeline_not_found(self):
        with pytest.raises(HTTPException):
            AnalyticsPipelineProcessor.delete_analytics_pipeline("b1", "69255e0feddf7785bcc0831b")

    def test_update_scheduled_task_normal(self):
        obj = AnalyticsPipelineConfig(
            pipeline_name="old",
            bot="b1",
            user="u1",
            status=True,
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="20 16 * * *", timezone="Asia/Kolkata")
        ).save()

        payload = {
            "pipeline_name": "new-name",
            "callback_name": "cb",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "30 20 * * *",
                "timezone": "Asia/Kolkata"
            },
            "data_deletion_policy": [],
            "triggers": []
        }

        AnalyticsPipelineProcessor.update_scheduled_task(
            str(obj.id), "b1", "updated_user", payload
        )

        updated = AnalyticsPipelineConfig.objects().get(id=obj.id)
        assert updated.pipeline_name == "new-name"
        assert updated.callback_name == "cb"
        assert updated.user == "updated_user"

    def test_update_scheduled_task_epoch_conversion(self):
        obj = AnalyticsPipelineConfig(
            pipeline_name="old",
            bot="b1",
            user="u1",
            status=True,
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="20 16 * * *", timezone="Asia/Kolkata")
        ).save()

        payload = {
            "pipeline_name": "epoch-event",
            "callback_name": "cb",
            "scheduler_config": {
                "expression_type": "epoch",
                "schedule": "1700000000",
                "timezone": "Asia/Kolkata",
            }
        }

        AnalyticsPipelineProcessor.update_scheduled_task(str(obj.id), "b1", "u2", payload)

        updated = AnalyticsPipelineConfig.objects().get(id=obj.id)
        assert updated.pipeline_name ==  "epoch-event"

    def test_update_scheduled_task_invalid_epoch(self):
        obj = AnalyticsPipelineConfig(
            pipeline_name="old",
            bot="b1",
            user="u1",
            status=True,
            scheduler_config=SchedulerConfiguration(expression_type="cron", schedule="30 20 * * *", timezone = "Asia/Kolkata")
        ).save()

        payload = {
            "pipeline_name": "bad",
            "callback_name": "cb",
            "scheduler_config": {
                "expression_type": "epoch",
                "schedule": "notanumber",
            }
        }

        with pytest.raises(AppException):
            AnalyticsPipelineProcessor.update_scheduled_task(str(obj.id), "b1", "u1", payload)

    def test_get_pipeline_code(self):
        data = {
            "bot": "b1",
            "name": "test_name",
            "pyscript_code": "print('Hello, World!')",
        }
        result = CallbackConfig.create_entry(**data)

        code = AnalyticsPipelineProcessor.get_pipeline_code("b1", "test_name")
        print(code)
        assert code == "print('Hello, World!')"

    def test_get_pipeline_code_not_found(self):
        with pytest.raises(AppException):
            AnalyticsPipelineProcessor.get_pipeline_code("b1", "missing")
