import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from bson import ObjectId
from mongoengine import connect, ValidationError, DoesNotExist

from kairon.exceptions import AppException
from kairon.shared.chat.broadcast.data_objects import MessageBroadcastLogs, MessageBroadcastSettings
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.data.constant import STATUSES
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
                "schedule": "* * * * *",
                "timezone": "Asia/Calcutta"
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
        with pytest.raises(ValidationError, match=f"Recurrence interval must be at least 86340 seconds!"):
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
            "scheduler_config": {
                "schedule": "2099-12-31T23:59:59",
                "timezone": "Asia/Kolkata",
                "expression_type":"epoch"
            },
            "recipients_config": {"recipients": "918958030541,"},
            "template_config": [{"template_id": "brochure_pdf"}],
        }
        result = MessageBroadcastProcessor.add_scheduled_task(bot, user, config)
        assert result


    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_add_one_time_scheduler_with_unkniwn_timezone(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "missing_run_at",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            "scheduler_config": {
                # missing run_at
                "expression_type": "epoch",
                "timezone": "xyvcd cdw ",
            },
            "recipients_config": {"recipients": "918958030541,"},
            "template_config": [{"template_id": "brochure_pdf"}],
        }
        with pytest.raises(ValidationError, match="Unknown timezone: xyvcd cdw"):
            MessageBroadcastProcessor.add_scheduled_task(bot, user, config)


    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_update_one_time_scheduler_success(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "updated_one_time_scheduler",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type":"epoch",
                "schedule": 4095161400,
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
        assert updated["scheduler_config"]["timezone"] == "Asia/Kolkata"


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

        with pytest.raises(AppException, match="scheduler_config is required!"):
            MessageBroadcastProcessor.update_scheduled_task(
                existing_config["_id"], bot, user, config
            )

    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_update_one_time_scheduler_with_invalid_epoch(self, mock_channel_config):
        bot = "test_schedule"
        user = "test_user"
        config = {
            "name": "updated_one_time_scheduler",
            "broadcast_type": "static",
            "connector_type": "whatsapp",
            "scheduler_config": {
                "expression_type":"epoch",
                "schedule": "mayank",
                "timezone": "Asia/Kolkata",
            },
            "recipients_config": {"recipients": "918958030541,"},
            "template_config": [{"template_id": "brochure_pdf"}],
        }

        existing_config = list(MessageBroadcastProcessor.list_settings(bot))[0]
        assert existing_config

        with pytest.raises(AppException, match="schedule must be a valid integer epoch time for 'epoch' type"):
            MessageBroadcastProcessor.update_scheduled_task(
                existing_config["_id"], bot, user, config
            )

    def test_update_retry_count_settings_not_found(self):
        notification_id = "test_notification_id"
        bot = "test_bot"
        user = "test_user"
        retry_count = 3

        with patch("kairon.shared.chat.broadcast.data_objects.MessageBroadcastSettings.objects") as mock_objects:
            mock_queryset = MagicMock()
            mock_queryset.get.side_effect = DoesNotExist("Not found")
            mock_objects.return_value = mock_queryset

            with pytest.raises(AppException, match="Notification settings not found!"):
                MessageBroadcastProcessor.update_retry_count(
                    notification_id=notification_id,
                    bot=bot,
                    user=user,
                    retry_count=retry_count
                )

def test_discovers_dynamic_numbered_params():
    bot = "test_bot_01"
    timestamp = datetime.utcnow()
    config = {
        "name": "test_broadcast", "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {
            "recipients": "919876543211,919012345678,919012341234"
        },
        "template_config": [
            {
                'language': 'hi',
                "template_id": "brochure_pdf",
            }
        ],
        "status": False,
        "retry_count": 1,
        "bot": bot,
        "user": "test_user"
    }
    template = [
        {
            "format": "TEXT",
            "text": "Kisan Suvidha Program Follow-up",
            "type": "HEADER"
        },
        {
            "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
            "type": "BODY"
        },
        {
            "text": "reply with STOP to unsubscribe",
            "type": "FOOTER"
        },
        {
            "buttons": [
                {
                    "text": "Connect to Agronomist",
                    "type": "QUICK_REPLY"
                }
            ],
            "type": "BUTTONS"
        }
    ]
    msg_broadcast_id = MessageBroadcastSettings(**config).save().id.__str__()
    MessageBroadcastLogs(
        **{
            "reference_id": "667bed955bfdaf3466b19de7",
            "log_type": "common",
            "bot": bot,
            "status": "Completed",
            "user": "test_user",
            "total": 3,
            "resend_count_1": 2,
            "skipped_count_1": 0,
            "event_id": msg_broadcast_id,
            "timestamp": timestamp,

        }
    ).save()
    timestamp = timestamp + timedelta(minutes=2)
    MessageBroadcastLogs(
        **{
            "reference_id": "667bed955bfdaf3466b19de7",
            "log_type": "send",
            "bot": bot,
            "status": STATUSES.SUCCESS.value,
            "template_name": "brochure_pdf",
            "template": template,
            "namespace": "54500467_f322_4595_becd_419af88spm4",
            "language_code": "hi",
            "errors": [],
            "api_response": {
                "messaging_product": "whatsapp",
                "contacts": [
                    {
                        "input": "919012345678",
                        "wa_id": "919012345678"
                    }
                ],
                "messages": [
                    {
                        "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ"
                    }
                ]
            },
            "recipient": "919012345678",
            "template_params": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                "filename": "Brochure.pdf",
                            },
                        }
                    ],
                }
            ],
            "timestamp": timestamp,
            "retry_count": 0
        }
    ).save()
    timestamp = timestamp + timedelta(minutes=2)
    MessageBroadcastLogs(
        **{
            "reference_id": "667bed955bfdaf3466b19de7",
            "log_type": "send",
            "bot": bot,
            "status": STATUSES.SUCCESS.value,
            "template_name": "brochure_pdf",
            "template": template,
            "namespace": "54500467_f322_4595_becd_419af88spm4",
            "language_code": "hi",
            "errors": [
                {
                    "code": 130472,
                    "title": "User's number is part of an experiment",
                    "message": "User's number is part of an experiment",
                    "error_data": {
                        "details": "Failed to send message because this user's phone number is part of an experiment"
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            "api_response": {
                "messaging_product": "whatsapp",
                "contacts": [
                    {
                        "input": "919876543211",
                        "wa_id": "919876543211"
                    }
                ],
                "messages": [
                    {
                        "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA=="
                    }
                ]
            },
            "recipient": "919876543211",
            "template_params_1": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                "filename": "Brochure.pdf",
                            },
                        }
                    ],
                }
            ],
            "timestamp": timestamp,
            "retry_count": 0
        }
    ).save()

    keys = MessageBroadcastProcessor.get_all_dynamic_keys(bot)

    assert "template_params_1" in keys
    assert "bot" in keys

def test_handles_no_logs_gracefully():
    bot_id = "non_existent_bot"
    keys = MessageBroadcastProcessor.get_all_dynamic_keys(bot_id)

    assert isinstance(keys, list)
    assert len(keys) == 0