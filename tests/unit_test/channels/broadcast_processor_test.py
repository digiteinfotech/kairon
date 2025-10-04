import os
from unittest.mock import patch

import pytest
from bson import ObjectId
from mongoengine import connect, ValidationError

from kairon.exceptions import AppException
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.utils import Utility


class TestMessageBroadcastProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_add_scheduler_task_channel_not_configured(self):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "57 22 * * *"
            },
            "recipients_config": {
                "recipient_type": "static",
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                }
            ]
        }
        with pytest.raises(AppException, match=f"Channel 'whatsapp' not configured!"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_scheduled_task(self, mock_channel_config):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "first_scheduler", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "57 22 * * *",
                "timezone": "Asia/Kolkata"
            },
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }
        assert MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

    def test_add_scheduler_exists(self):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "first_scheduler", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "57 22 * * *"
            },
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }
        with pytest.raises(AppException, match=f"Schedule with name '{config['name']}' exists!"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_scheduler_one_time_trigger(self, mock_channel_config):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "second_scheduler", "broadcast_type": "static",
            "connector_type": "slack",
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }
        assert MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_scheduler_one_time_trigger_errors(self, mock_channel_config):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "test_add_scheduler_one_time_trigger_errors", "broadcast_type": "static",
            "connector_type": "slack",
        }
        with pytest.raises(ValidationError, match="recipients_config and template_config is required for static broadcasts!"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

        config = {
            "name": "test_add_scheduler_one_time_trigger_errors", "broadcast_type": "dynamic",
            "recipients_config": {
                "recipients": "918958030541, "
            }, "connector_type": "slack",
        }
        with pytest.raises(ValidationError, match="pyscript is required for dynamic broadcasts!"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_scheduled_task_invalid_schedule(self, mock_channel_config):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "third_scheduler", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "* * * * *"
            },
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }
        with pytest.raises(ValidationError, match=f"recurrence interval must be at least 86340 seconds!"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

        config["scheduler_config"]["schedule"] = ""
        with pytest.raises(ValidationError, match="Invalid cron expression: ''"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_update_scheduled_task(self, mock_channel_config):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "first_scheduler", "broadcast_type": "dynamic",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "30 22 5 * *",
                "timezone": "Asia/Kolkata"
            },
            "pyscript": "send_msg('template_name', '9876543210')"
        }
        first_scheduler_config = list(MessageBroadcastProcessor.list_settings(bot, name="first_scheduler"))[0]
        assert first_scheduler_config

        MessageBroadcastProcessor.update_scheduled_task(first_scheduler_config["_id"], bot, user, config)

    def test_updated_scheduled_task_not_exists(self):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "first_scheduler", "broadcast_type": "dynamic",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "30 22 5 * *"
            },
            "pyscript": "send_msg('template_name', '9876543210')"
        }
        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.update_scheduled_task(ObjectId().__str__(), bot, user, config)

    def test_update_schedule_invalid_scheduler(self):
        bot = "test_achedule"
        user = "test_user"
        first_scheduler_config = list(MessageBroadcastProcessor.list_settings(bot, name="first_scheduler"))[0]
        assert first_scheduler_config
        first_scheduler_config["scheduler_config"] = None
        with pytest.raises(AppException, match="scheduler_config is required!"):
            MessageBroadcastProcessor.update_scheduled_task(first_scheduler_config["_id"], bot, user, first_scheduler_config)

    def test_get_settings(self):
        bot = "test_achedule"
        settings = list(MessageBroadcastProcessor.list_settings(bot))
        config_id = settings[0].pop("_id")
        assert isinstance(config_id, str)
        config_id = settings[1].pop("_id")
        assert isinstance(config_id, str)
        settings[0].pop("timestamp")
        settings[1].pop("timestamp")
        assert settings == [{'name': 'first_scheduler', 'connector_type': 'whatsapp',
                             "broadcast_type": "dynamic", 'retry_count': 0, 'collection_config': {},
                             'scheduler_config': {'expression_type': 'cron', 'schedule': '30 22 5 * *',
                                                  "timezone": "Asia/Kolkata"},
                             "pyscript": "send_msg('template_name', '9876543210')", "template_config": [],
                             'bot': 'test_achedule', 'user': 'test_user', 'status': True},
                            {'name': 'second_scheduler', 'connector_type': 'slack', 'collection_config': {},
                            'recipients_config': {'recipients': '918958030541,'}, 'retry_count': 0,
                             "broadcast_type": "static", 'template_config': [{'template_id': 'brochure_pdf', 'language': 'en'}],
                             'bot': 'test_achedule', 'user': 'test_user', 'status': True}]

        setting = MessageBroadcastProcessor.get_settings(config_id, bot)
        assert isinstance(setting.pop("_id"), str)
        setting.pop("timestamp")
        assert setting == {'name': 'second_scheduler', 'connector_type': 'slack', 'retry_count': 0,
                           'collection_config': {},
                           'recipients_config': {'recipients': '918958030541,'}, 'broadcast_type': 'static',
                           'template_config': [{'template_id': 'brochure_pdf', "language": "en"}],
                           'bot': 'test_achedule', 'user': 'test_user', 'status': True}

    def test_get_settings_not_found(self):
        bot = "test_schedule"
        assert [] == list(MessageBroadcastProcessor.list_settings(bot, name="first_scheduler"))

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(ObjectId().__str__(), bot)

    def test_delete_schedule(self):
        bot = "test_achedule"
        first_scheduler_config = list(MessageBroadcastProcessor.list_settings(bot, name="first_scheduler"))[0]
        MessageBroadcastProcessor.delete_task(first_scheduler_config["_id"], bot, False)

        settings = list(MessageBroadcastProcessor.list_settings(bot, status=True))
        config_id = settings[0].pop("_id")
        assert isinstance(config_id, str)
        settings[0].pop("timestamp")
        assert settings == [{'name': 'second_scheduler', 'connector_type': 'slack',
                             "broadcast_type": "static", 'collection_config': {},
                             'recipients_config': {'recipients': '918958030541,'}, 'retry_count': 0,
                             'template_config': [{'template_id': 'brochure_pdf', "language": "en"}],
                             'bot': 'test_achedule', 'user': 'test_user', 'status': True}]

        settings = list(MessageBroadcastProcessor.list_settings(bot, status=False))
        config_id = settings[0].pop("_id")
        assert isinstance(config_id, str)
        settings[0].pop("timestamp")
        assert settings == [{'name': 'first_scheduler', 'connector_type': 'whatsapp',
                             "broadcast_type": "dynamic", "template_config": [], 'collection_config': {},
                             'scheduler_config': {'expression_type': 'cron', 'schedule': '30 22 5 * *', "timezone": "Asia/Kolkata"},
                             "pyscript": "send_msg('template_name', '9876543210')", 'retry_count': 0,
                             'bot': 'test_achedule', 'user': 'test_user', 'status': False}]

    def test_delete_schedule_not_exists(self):
        bot = "test_achedule"
        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.delete_task(ObjectId().__str__(), bot)

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.delete_task(ObjectId().__str__(), bot, True)

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_scheduled_broadcast_task(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "schedule_broadcast", "broadcast_type": "dynamic",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "57 22 * * *",
                "timezone": "Asia/Kolkata"
            },
            "pyscript": "send_msg('template_name', '9876543210')"
        }
        message_broadcast_id = MessageBroadcastProcessor.add_scheduled_task(bot, user, config)
        assert message_broadcast_id

    def test_get_broadcast_settings_scheduled(self):
        bot = "test_schedule"
        settings = list(MessageBroadcastProcessor.list_settings(bot))
        config_id = settings[0].pop("_id")
        assert isinstance(config_id, str)
        settings[0].pop("timestamp")
        assert settings == [
            {
                'name': 'schedule_broadcast',
                'connector_type': 'whatsapp',
                "broadcast_type": "dynamic",
                'collection_config': {},
                'retry_count': 0,
                'scheduler_config': {
                    'expression_type': 'cron',
                    'schedule': '57 22 * * *',
                    "timezone": "Asia/Kolkata"
                },
                "pyscript": "send_msg('template_name', '9876543210')",
                "template_config": [],
                'bot': 'test_schedule',
                'user': 'test_user',
                'status': True
            }
        ]

        setting = MessageBroadcastProcessor.get_settings(config_id, bot)
        assert isinstance(setting.pop("_id"), str)
        setting.pop("timestamp")
        assert setting == {
            'name': 'schedule_broadcast',
            'connector_type': 'whatsapp',
            "broadcast_type": "dynamic",
            'collection_config': {},
            'retry_count': 0,
            'scheduler_config': {
                'expression_type': 'cron',
                'schedule': '57 22 * * *',
                "timezone": "Asia/Kolkata"
            },
            "pyscript": "send_msg('template_name', '9876543210')",
            "template_config": [],
            'bot': 'test_schedule',
            'user': 'test_user',
            'status': True
        }
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_one_time_scheduler_success(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "one_time_scheduler_success",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            "one_time_scheduler_config": {
                "run_at": "2099-12-31T23:59:59",
                "timezone": "Asia/Kolkata",
            },
            "recipients_config": {"recipients": "918958030541,"},
            "template_config": [{"template_id": "brochure_pdf"}],
        }
        result = MessageBroadcastProcessor.add_scheduled_task(bot, user, config)
        assert result


    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_one_time_scheduler_missing_run_at(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "missing_run_at",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            "one_time_scheduler_config": {
                # missing run_at
                "timezone": "Asia/Kolkata",
            },
            "recipients_config": {"recipients": "918958030541,"},
            "template_config": [{"template_id": "brochure_pdf"}],
        }
        with pytest.raises(ValidationError, match="run_at datetime is required for one-time scheduling!"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)


    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_update_one_time_scheduler_success(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "updated_one_time_scheduler",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            "one_time_scheduler_config": {
                "run_at": "2099-12-31T23:59:59",
                "timezone": "Asia/Kolkata",
            },
            "recipients_config": {"recipients": "918958030541,"},
            "template_config": [{"template_id": "brochure_pdf"}],
        }

        existing_config = list(MessageBroadcastProcessor.list_settings(bot))[0]
        assert existing_config

        # Perform update
        MessageBroadcastProcessor.update_scheduled_task(
            existing_config["_id"], bot, user, config
        )

        updated = MessageBroadcastProcessor.get_settings(existing_config["_id"], bot)
        assert updated["name"] == config["name"]
        assert updated["one_time_scheduler_config"]["timezone"] == "Asia/Kolkata"

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_update_one_time_scheduler_with_both_config(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "missing_one_time_config",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            "one_time_scheduler_config": {
                "run_at": "2099-12-31T23:59:59",
                "timezone": "Asia/Kolkata",
            },
            'scheduler_config': {
                'expression_type': 'cron',
                'schedule': '57 22 * * *',
                "timezone": "Asia/Kolkata"
            }

        }

        existing_config = list(MessageBroadcastProcessor.list_settings(bot))[0]
        assert existing_config

        with pytest.raises(AppException, match="Only one of scheduler_config or one_time_scheduler_config can be provided!"):
            MessageBroadcastProcessor.update_scheduled_task(
                existing_config["_id"], bot, user, config
            )


    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_update_one_time_scheduler_missing_config(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "missing_one_time_config",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            # missing one_time_scheduler_config
        }

        existing_config = list(MessageBroadcastProcessor.list_settings(bot))[0]
        assert existing_config

        with pytest.raises(AppException, match="scheduler_config or one_time_scheduler_config is required!"):
            MessageBroadcastProcessor.update_scheduled_task(
                existing_config["_id"], bot, user, config
            )


