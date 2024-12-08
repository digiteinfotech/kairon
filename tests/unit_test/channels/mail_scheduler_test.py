
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

@patch('kairon.shared.channels.mail.scheduler.Utility.get_event_server_url')
@patch('kairon.shared.channels.mail.scheduler.Utility.execute_http_request')
def test_request_epoch_failure(mock_execute_http_request, mock_get_event_server_url):
    mock_get_event_server_url.return_value = "http://localhost"
    mock_execute_http_request.return_value = {'success': False}

    with pytest.raises(AppException):
        MailScheduler.request_epoch("test_bot")


# @patch("kairon.shared.channels.mail.processor.MailProcessor.read_mails")
# @patch("kairon.shared.channels.mail.scheduler.MailChannelScheduleEvent.enqueue")
# @patch("kairon.shared.channels.mail.scheduler.datetime")
# def test_read_mailbox_and_schedule_events(mock_datetime, mock_enqueue, mock_read_mails):
#     bot = "test_bot"
#     fixed_now = datetime(2024, 12, 1, 20, 41, 55, 390288)
#     mock_datetime.now.return_value = fixed_now
#     mock_read_mails.return_value = ([
#         {"subject": "Test Subject", "mail_id": "test@example.com", "date": "2023-10-10", "body": "Test Body"}
#     ], "mail_channel_test_user_acc", 1200)
#     next_timestamp = MailScheduler.read_mailbox_and_schedule_events(bot)
#     mock_read_mails.assert_called_once_with(bot)
#     mock_enqueue.assert_called_once()
#     assert next_timestamp == fixed_now + timedelta(seconds=1200)