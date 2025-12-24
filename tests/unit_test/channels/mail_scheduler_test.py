
import pytest
from unittest.mock import patch
import os
from kairon import Utility
from kairon.exceptions import AppException

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from kairon.shared.channels.mail.scheduler import MailScheduler

@pytest.fixture
def setup_environment():
    with patch("pymongo.MongoClient") as mock_client, \
         patch("kairon.shared.chat.data_objects.Channels.objects") as mock_channels, \
         patch("kairon.shared.channels.mail.processor.MailProcessor.read_mails") as mock_read_mails, \
         patch("apscheduler.schedulers.background.BackgroundScheduler", autospec=True) as mock_scheduler:

        mock_client_instance = mock_client.return_value
        mock_channels.return_value = [{'bot': 'test_bot_1'}, {'bot': 'test_bot_2'}]
        mock_read_mails.return_value = ([], 'test@user.com', 60)  # Mock responses and next_delay
        mock_scheduler_instance = mock_scheduler.return_value
        yield {
            'mock_client': mock_client_instance,
            'mock_channels': mock_channels,
            'mock_read_mails': mock_read_mails,
            'mock_scheduler': mock_scheduler_instance
        }


@patch('kairon.shared.channels.mail.processor.MailProcessor.validate_smtp_connection')
@patch('kairon.shared.channels.mail.processor.MailProcessor.validate_imap_connection')
@patch('kairon.shared.channels.mail.scheduler.Utility.get_event_server_url')
@patch('kairon.shared.channels.mail.scheduler.Utility.execute_http_request')
def test_request_epoch_success(mock_execute_http_request, mock_get_event_server_url, mock_imp, mock_smpt):
    mock_get_event_server_url.return_value = "http://localhost"
    mock_execute_http_request.return_value = {'success': True}
    bot = "test_bot"
    try:
        MailScheduler.request_epoch(bot)
    except AppException:
        pytest.fail("request_epoch() raised AppException unexpectedly!")

@patch('kairon.shared.channels.mail.processor.MailProcessor.validate_smtp_connection')
@patch('kairon.shared.channels.mail.processor.MailProcessor.validate_imap_connection')
@patch('kairon.shared.channels.mail.scheduler.Utility.get_event_server_url')
@patch('kairon.shared.channels.mail.scheduler.Utility.execute_http_request')
def test_request_epoch__response_not_success(mock_execute_http_request, mock_get_event_server_url, mock_imp, mock_smpt):
    mock_get_event_server_url.return_value = "http://localhost"
    mock_execute_http_request.return_value = {'success': False}
    bot = "test_bot"
    with pytest.raises(AppException):
        MailScheduler.request_epoch(bot)


@patch('kairon.shared.channels.mail.scheduler.Utility.get_event_server_url')
@patch('kairon.shared.channels.mail.scheduler.Utility.execute_http_request')
def test_request_epoch_failure(mock_execute_http_request, mock_get_event_server_url):
    mock_get_event_server_url.return_value = "http://localhost"
    mock_execute_http_request.return_value = {'success': False}

    with pytest.raises(AppException):
        MailScheduler.request_epoch("test_bot")



@patch('kairon.events.utility.KScheduler.add_job')
@patch('kairon.events.utility.KScheduler.update_job')
@patch('kairon.events.utility.KScheduler.__init__', return_value=None)
@patch('kairon.shared.channels.mail.processor.MailProcessor')
@patch('pymongo.MongoClient', autospec=True)
def test_schedule_channel_mail_reading(mock_mongo, mock_mail_processor, mock_kscheduler, mock_update_job, mock_add_job,monkeypatch):
    from kairon.events.utility import EventUtility

    bot = "test_bot"
    mock_mail_processor_instance = mock_mail_processor.return_value
    mock_mail_processor_instance.config = {"interval": 1}
    mock_mail_processor_instance.state.event_id = None
    mock_mail_processor_instance.bot_settings.user = "test_user"
    mock_mail_processor_instance.Utility.user = "test_user"
    monkeypatch.setitem(
        Utility.environment,
        "integrations",
        {"email": {"interval": "1"}},
    )
#     # Test case when event_id is None
    EventUtility.schedule_channel_mail_reading(bot)
    mock_add_job.assert_called_once()
    mock_update_job.assert_not_called()

    mock_add_job.reset_mock()
    mock_update_job.reset_mock()
    mock_mail_processor_instance.state.event_id = "existing_event_id"

    # Test case when event_id exists
    EventUtility.schedule_channel_mail_reading(bot)
    mock_update_job.assert_called_once()
    mock_add_job.assert_not_called()

@patch('kairon.events.utility.KScheduler.add_job')
@patch('kairon.events.utility.KScheduler', autospec=True)
@patch('kairon.shared.channels.mail.processor.MailProcessor')
@patch('pymongo.MongoClient', autospec=True)
def test_schedule_channel_mail_reading_exception(mock_mongo_client, mock_mail_processor, mock_kscheduler, mock_add_job):
    from kairon.events.utility import EventUtility

    bot = "test_bot"
    mock_mail_processor.side_effect = Exception("Test Exception")

    with pytest.raises(AppException) as excinfo:
        EventUtility.schedule_channel_mail_reading(bot)
    assert str(excinfo.value) == f"Failed to schedule mail reading for bot {bot}. Error: Test Exception"

@patch('kairon.events.utility.KScheduler.delete_job')
@patch('kairon.events.utility.KScheduler.__init__', return_value=None)
@patch('kairon.shared.channels.mail.processor.MailProcessor')
@patch('pymongo.MongoClient', autospec=True)
def test_stop_channel_mail_reading(mock_mongo, mock_mail_processor, mock_kscheduler, mock_delete_job):
    from kairon.events.utility import EventUtility

    bot = "test_bot"
    mock_mail_processor_instance = mock_mail_processor.return_value
    mock_mail_processor_instance.config = {"interval": 1}
    mock_mail_processor_instance.state.event_id = 'existing_event_id'
    mock_mail_processor_instance.bot_settings.user = "test_user"

#     # Test case when event_id is None
    EventUtility.stop_channel_mail_reading(bot)
    mock_delete_job.assert_called_once()

@patch('kairon.shared.utils.Utility.is_exist')
@patch('kairon.shared.channels.mail.scheduler.Utility.get_event_server_url')
@patch('kairon.shared.channels.mail.scheduler.Utility.execute_http_request')
def test_request_stop_success(mock_execute_http_request, mock_get_event_server_url, mock_imp):
    mock_get_event_server_url.return_value = "http://localhost"
    mock_execute_http_request.return_value = {'success': True}
    mock_imp.return_value = True
    bot = "test_bot"
    try:
        MailScheduler.request_stop(bot)
    except AppException:
        pytest.fail("request_epoch() raised AppException unexpectedly!")


@patch('kairon.shared.utils.Utility.is_exist')
@patch('kairon.shared.channels.mail.scheduler.Utility.get_event_server_url')
@patch('kairon.shared.channels.mail.scheduler.Utility.execute_http_request')
def test_request_stop_response_not_success(mock_execute_http_request, mock_get_event_server_url, mock_imp):
    mock_get_event_server_url.return_value = "http://localhost"
    mock_execute_http_request.return_value = {'success': False}
    mock_imp.return_value = True
    bot = "test_bot"
    with pytest.raises(AppException):
        MailScheduler.request_stop(bot)

@patch('kairon.shared.utils.Utility.is_exist')
@patch('kairon.shared.channels.mail.scheduler.Utility.get_event_server_url')
@patch('kairon.shared.channels.mail.scheduler.Utility.execute_http_request')
def test_request_stop_no_channel_exist_exception(mock_execute_http_request, mock_get_event_server_url, mock_imp):
    mock_get_event_server_url.return_value = "http://localhost"
    mock_execute_http_request.return_value = {'success': True}
    mock_imp.return_value = False
    bot = "test_bot"
    with pytest.raises(AppException):
        MailScheduler.request_stop(bot)

