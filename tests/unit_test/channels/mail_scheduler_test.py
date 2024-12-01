import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import os
from kairon import Utility
os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from kairon.shared.channels.mail.scheduler import MailScheduler

@pytest.fixture
def setup_environment():
    with patch("pymongo.MongoClient") as mock_client, \
         patch("kairon.shared.chat.data_objects.Channels.objects") as mock_channels, \
         patch("kairon.shared.channels.mail.processor.MailProcessor.process_mails", new_callable=AsyncMock) as mock_process_mails, \
         patch("apscheduler.schedulers.background.BackgroundScheduler", autospec=True) as mock_scheduler:

        mock_client_instance = mock_client.return_value
        mock_channels.return_value = MagicMock(values_list=MagicMock(return_value=[{'bot': 'test_bot_1'}, {'bot': 'test_bot_2'}]))
        mock_process_mails.return_value = ([], 60)  # Mock responses and next_delay
        mock_scheduler_instance = mock_scheduler.return_value
        yield {
            'mock_client': mock_client_instance,
            'mock_channels': mock_channels,
            'mock_process_mails': mock_process_mails,
            'mock_scheduler': mock_scheduler_instance
        }

@pytest.mark.asyncio
async def test_mail_scheduler_epoch(setup_environment):
    # Arrange
    mock_scheduler = setup_environment['mock_scheduler']
    MailScheduler.mail_queue_name = "test_queue"
    MailScheduler.scheduler = mock_scheduler

    # Act
    MailScheduler.epoch()

    # Assert
    mock_scheduler.add_job.assert_called()

@pytest.mark.asyncio
async def test_mail_scheduler_process_mails(setup_environment):
    mock_process_mails = setup_environment['mock_process_mails']
    mock_scheduler = setup_environment['mock_scheduler']
    MailScheduler.scheduled_bots.add("test_bot_1")
    MailScheduler.scheduler = mock_scheduler

    await MailScheduler.process_mails("test_bot_1", mock_scheduler)

    mock_process_mails.assert_awaited_once_with("test_bot_1", mock_scheduler)
    assert "test_bot_1" in MailScheduler.scheduled_bots


@pytest.fixture
def setup_environment2():
    with patch("pymongo.MongoClient") as mock_client, \
         patch("kairon.shared.chat.data_objects.Channels.objects") as mock_channels, \
         patch("kairon.shared.channels.mail.processor.MailProcessor.process_mails", new_callable=AsyncMock) as mock_process_mails, \
         patch("apscheduler.jobstores.mongodb.MongoDBJobStore.__init__", return_value=None) as mock_jobstore_init:

        mock_client_instance = mock_client.return_value
        mock_channels.return_value = MagicMock(values_list=MagicMock(return_value=[{'bot': 'test_bot_1'}, {'bot': 'test_bot_2'}]))
        mock_process_mails.return_value = ([], 60)

        yield {
            'mock_client': mock_client_instance,
            'mock_channels': mock_channels,
            'mock_process_mails': mock_process_mails,
            'mock_jobstore_init': mock_jobstore_init,
        }


@pytest.mark.asyncio
async def test_mail_scheduler_epoch_creates_scheduler(setup_environment2):
    with patch("apscheduler.schedulers.background.BackgroundScheduler.start", autospec=True) as mock_start, \
            patch("apscheduler.schedulers.background.BackgroundScheduler.add_job", autospec=True) as mock_add_job:
        MailScheduler.scheduler = None

        started = MailScheduler.epoch()

        assert started
        assert MailScheduler.scheduler is not None
        mock_start.assert_called_once()
