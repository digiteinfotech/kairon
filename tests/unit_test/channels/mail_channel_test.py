import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from croniter.croniter import CroniterError
from imap_tools import MailMessage
from mongoengine import connect, disconnect


from kairon import Utility
from kairon.shared.channels.mail.data_objects import MailResponseLog, MailChannelStateData, MailStatus

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from kairon.shared.account.data_objects import Bot, Account
from kairon.shared.channels.mail.constants import MailConstants
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.chat.data_objects import Channels
from kairon.shared.data.data_objects import BotSettings

from kairon.exceptions import AppException
from kairon.shared.constants import ChannelTypes




class TestMailChannel:
    bot_id = ""
    user = "mail_channel_test_user"

    @classmethod
    def setup_class(cls):
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

        a = Account(name="mail_channel_test_user_acc", user=cls.user).save()
        bot = Bot(name="mail_channel_test_bot", user=cls.user, status=True,
                                 account=a.id).save()
        BotSettings(bot=str(bot.id), user=cls.user).save()
        cls.bot_id = str(bot.id)

    @classmethod
    def teardown_class(cls):
        BotSettings.objects(user=cls.user).delete()
        Bot.objects(user=cls.user).delete()
        Account.objects(user=cls.user).delete()
        Channels.objects(connector_type=ChannelTypes.MAIL.value).delete()

        disconnect()



    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.execute_http_request")
    def test_login_imap(self, execute_http_req, mock_get_channel_config, mock_mailbox):
        execute_http_req.return_value = {"success": True}
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance
        mock_mailbox_instance.login.return_value = ("OK", ["Logged in"])
        mock_mailbox_instance._simple_command.return_value = ("OK", ["Logged in"])
        mock_mailbox_instance.select.return_value = ("OK", ["INBOX"])

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com"
            }
        }

        bot_id = self.bot_id
        mp = MailProcessor(bot=bot_id)
        mp.login_imap()

        mock_get_channel_config.assert_called_once_with(ChannelTypes.MAIL, bot_id, False)
        mock_mailbox.assert_called_once_with("imap.testuser.com")
        mock_mailbox_instance.login.assert_called_once_with("mail_channel_test_user_acc@testuser.com", "password")



    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.execute_http_request")
    def test_login_imap_logout(self,execute_http_request, mock_get_channel_config, mock_mailbox):
        execute_http_request.return_value = {"success": True}
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance
        mock_mailbox_instance.login.return_value = mock_mailbox_instance  # Ensure login returns the instance
        mock_mailbox_instance._simple_command.return_value = ("OK", ["Logged in"])
        mock_mailbox_instance.select.return_value = ("OK", ["INBOX"])


        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com"
            }
        }

        bot_id = self.bot_id
        mp = MailProcessor(bot=bot_id)

        mp.login_imap()
        mp.logout_imap()

        mock_mailbox_instance.logout.assert_called_once()


    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    def test_login_smtp(self, mock_get_channel_config, mock_smtp):
        # Arrange
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }

        bot_id = self.bot_id
        mp = MailProcessor(bot=bot_id)

        mp.login_smtp()

        mock_get_channel_config.assert_called_once_with(ChannelTypes.MAIL, bot_id, False)
        mock_smtp.assert_called_once_with("smtp.testuser.com", 587, timeout=30)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("mail_channel_test_user_acc@testuser.com", "password")


    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    def test_logout_smtp(self, mock_get_channel_config, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }

        bot_id = self.bot_id
        mp = MailProcessor(bot=bot_id)

        mp.login_smtp()
        mp.logout_smtp()

        mock_smtp_instance.quit.assert_called_once()
        assert mp.smtp is None



    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail(self, mock_get_channel_config, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mail_response_log = MailResponseLog(bot=self.bot_id,
                                            sender_id="recipient@test.com",
                                            user="mail_channel_test_user_acc",
                                            uid=123
                                            )
        mail_response_log.save()
        mail_response_log.save()

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }
        bot_id = self.bot_id
        mp = MailProcessor(bot=bot_id)
        mp.login_smtp()

        await mp.send_mail("recipient@test.com", "Test Subject", "Test Body", mail_response_log.id)

        MailResponseLog.objects().delete()

        from email import message_from_string
        mock_smtp_instance.sendmail.assert_called_once()
        call_args = mock_smtp_instance.sendmail.call_args[0]
        assert call_args[0] == "mail_channel_test_user_acc@testuser.com"
        assert call_args[1] == ["recipient@test.com"]
        parsed = message_from_string(call_args[2])
        assert "Test_Subject" in str(parsed['Subject'])
        body_part = parsed.get_payload()
        if isinstance(body_part, list):
            body_part = body_part[0].get_payload(decode=True).decode('utf-8')
        assert "Test Body" in body_part

    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail_exception(self, mock_get_channel_config, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mail_response_log = MailResponseLog(bot=self.bot_id,
                                            sender_id="recipient@test.com",
                                            user="mail_channel_test_user_acc",
                                            uid=123
                                            )
        mail_response_log.save()

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }

        bot_id = self.bot_id
        mp = MailProcessor(bot=bot_id)
        mp.login_smtp()

        mock_smtp_instance.sendmail.side_effect = Exception("SMTP error")

        await mp.send_mail("recipient@test.com", "Test Subject", "Test Body", mail_response_log.id)

        log = MailResponseLog.objects.get(id=mail_response_log.id)
        print(log.to_mongo())
        assert log.status == MailStatus.FAILED.value
        assert log.responses == ['SMTP error']
        MailResponseLog.objects().delete()



    @patch("kairon.shared.channels.mail.processor.ChatDataProcessor.get_channel_config")
    def test_process_mail(self,  mock_get_channel_config):
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com"
            }
        }

        mail_response_log = MailResponseLog(bot=self.bot_id,
                                            sender_id="recipient@test.com",
                                            user="mail_channel_test_user_acc",
                                            uid=123
                                            )
        mail_response_log.save()

        bot_id = self.bot_id
        mp = MailProcessor(bot=bot_id)

        rasa_chat_response = {
            "slots": {"name": "John Doe"},
            "response": [{"text": "How can I help you today?"}]
        }
        result = mp.process_mail( rasa_chat_response, mail_response_log.id)
        assert result == MailConstants.DEFAULT_TEMPLATE.format(bot_response="How can I help you today?")


        rasa_chat_response = {
            "slots": {"name": "John Doe"},
            "response": [{"text": "How can I help you today?"}]
        }
        mp.mail_template = "Hello {name}, {bot_response}"
        result = mp.process_mail(rasa_chat_response, mail_response_log.id)
        MailResponseLog.objects().delete()
        assert result == "Hello John Doe, How can I help you today?"



    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_generate_criteria(self, mock_get_channel_config):
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }

        mp = MailProcessor(bot=bot_id)
        mp.state.last_email_uid = 123
        #seen
        criteria = mp.generate_criteria(read_status="seen")
        print(criteria)
        assert criteria == '((SEEN) (UID 124:*))'

        #unseen
        criteria = mp.generate_criteria(read_status="unseen")
        assert criteria == '((UNSEEN) (UID 124:*))'

        #default
        criteria = mp.generate_criteria()
        assert criteria == '((UID 124:*))'

        #subjects
        criteria = mp.generate_criteria(subjects=["Test Subject", "another test subject"])
        assert criteria == '((OR SUBJECT "Test Subject" SUBJECT "another test subject") (UID 124:*))'

        #from
        criteria = mp.generate_criteria(from_addresses=["info", "important1@gmail.com", "anotherparrtern@gmail.com"])
        assert criteria == '((OR OR FROM "anotherparrtern@gmail.com" FROM "important1@gmail.com" FROM "info") (UID 124:*))'

        #mix
        criteria = mp.generate_criteria(read_status="unseen",
                                        subjects=["Test Subject", "another test subject", "happy"],
                                        ignore_subjects=['cat'],
                                        ignore_from=["info", "nomreply"],
                                        from_addresses=["@digite.com", "@nimblework.com"])

        assert criteria == '((UNSEEN) (OR OR SUBJECT "Test Subject" SUBJECT "another test subject" SUBJECT "happy") NOT ((SUBJECT "cat")) (OR FROM "@digite.com" FROM "@nimblework.com") NOT ((FROM "info")) NOT ((FROM "nomreply")) (UID 124:*))'

    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    def test_generate_criteria_with_last_email_uid_zero(self, mock_get_channel_config):
        import pytz
        from datetime import datetime
        bot_id = self.bot_id

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
                'interval': "*/30 * * * *"
            }
        }
        IST = pytz.timezone("Asia/Kolkata")

        fixed_now = IST.localize(datetime(2026, 1, 20, 12, 0, 0))
        fixed_prev = IST.localize(datetime(2026, 1, 20, 11, 30, 0))

        with patch("kairon.shared.channels.mail.processor.croniter") as mock_croniter:
            mock_iter = MagicMock()
            mock_iter.get_prev.return_value = fixed_prev
            mock_croniter.return_value = mock_iter
            mp = MailProcessor(bot=bot_id)
            mp.state.last_email_uid = 0

            criteria = mp.generate_criteria()
            assert criteria == '((SINCE 20-Jan-2026))'

            criteria = mp.generate_criteria(read_status="unseen")
            assert criteria == '((UNSEEN) (SINCE 20-Jan-2026))'

            criteria = mp.generate_criteria(read_status="seen")
            assert criteria == '((SEEN) (SINCE 20-Jan-2026))'

    @patch("kairon.shared.channels.mail.processor.croniter")
    @patch("kairon.shared.channels.mail.processor.datetime")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    def test_generate_criteria_cron_exception_fallback(self, mock_get_channel_config, mock_datetime, mock_croniter):
        """
        Test fallback behavior when croniter raises an exception
        """
        import pytz
        IST = pytz.timezone("Asia/Kolkata")
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
                'interval': "invalid cron"
            }
        }

        fixed_now = IST.localize(datetime(2024, 1, 10, 12, 0, 0))
        mock_datetime.now.return_value = fixed_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        mock_croniter.side_effect = CroniterError("Invalid cron")

        mp = MailProcessor(bot=bot_id)
        mp.state.last_email_uid = 0
        mp.config = {"interval": "invalid cron"}  # triggers exception

        criteria = mp.generate_criteria()

        assert criteria == f'((SINCE 10-Jan-2024))'

    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails(self, mock_get_channel_config,
                                  mock_mailbox, mock_process_message_task,
                                 mock_logout_imap):
        bot_id = self.bot_id

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }


        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_mail_message = MagicMock(spec=MailMessage)
        mock_mail_message.subject = "Test Subject"
        mock_mail_message.from_ = "test@example.com"
        mock_mail_message.date = "2023-10-10"
        mock_mail_message.text = "Test Body"
        mock_mail_message.html = None
        mock_mail_message.uid = "99000"
        mock_mail_message.headers = MagicMock()
        mock_mail_message.headers.get.side_effect = lambda key, default=None: \
            ['<msg-test@example.com>'] if key == 'message-id' else (default or [])
        mock_mail_message.attachments = []

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [mock_mail_message]

        mails, user = MailProcessor.read_mails(bot_id)
        print(mails)
        assert len(mails) == 1
        assert mails[0]["subject"] == "Test Subject"
        assert mails[0]["mail_id"] == "test@example.com"
        assert mails[0]["date"] == "2023-10-10"
        assert mails[0]["body"] == "Test Body"
        assert mails[0]["is_followup"] is False
        assert mails[0]["parent_log_id"] is None
        assert user == 'mail_channel_test_user'




    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_no_messages(self, mock_get_channel_config,
                                              mock_mailbox, mock_process_message_task,
                                             mock_logout_imap):
        bot_id = self.bot_id

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
                }
        }


        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = []

        mails, user = MailProcessor.read_mails(bot_id)
        assert len(mails) == 0
        assert user == 'mail_channel_test_user'

        mock_logout_imap.assert_called_once()



    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.login_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.send_mail")
    @patch("kairon.shared.chat.agent.agent_flow.AgenticFlow.execute_rule")
    @pytest.mark.asyncio
    async def test_process_messages(self, mock_process_messages_via_bot, mock_send_mail, mock_logout_smtp, mock_login_smtp, mock_get_channel_config):

        mail_response_log = MailResponseLog(bot=self.bot_id,
                                            sender_id="recipient@test.com",
                                            user="mail_channel_test_user_acc",
                                            uid=123
                                            )
        mail_response_log.save()


        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }

        bot = self.bot_id
        batch = [{"mail_id": "test@example.com", "subject": "Test Subject", "date": "2023-10-10", "body": "Test Body", "log_id": str(mail_response_log.id)}]

        mock_process_messages_via_bot.return_value = [{"text": "hello world"}], []

        await MailProcessor.process_messages(bot, batch)

        # Assert
        mock_process_messages_via_bot.assert_called_once()
        mock_login_smtp.assert_called_once()
        mock_send_mail.assert_called_once()
        mock_logout_smtp.assert_called_once()
        MailResponseLog.objects().delete()


    @patch("kairon.shared.channels.mail.processor.MailProcessor.login_smtp")
    @pytest.mark.asyncio
    async def test_process_messages_exception(self, mock_exc):
        # Arrange
        bot = "test_bot"
        batch = [{"mail_id": "test@example.com", "subject": "Test Subject", "date": "2023-10-10", "body": "Test Body"}]
        mock_exc.side_effect = Exception("Test Exception")

        # Act & Assert
        with pytest.raises(AppException):
            await MailProcessor.process_messages(bot, batch)

    @patch('kairon.shared.channels.mail.processor.MailProcessor.__init__')
    @patch('kairon.shared.channels.mail.processor.MailProcessor.login_smtp')
    @patch('kairon.shared.channels.mail.processor.MailProcessor.logout_smtp')
    def test_validate_smpt_connection(self, mp, mock_logout_smtp, mock_login_smtp):
        mp.return_value = None
        mock_login_smtp.return_value = None
        mock_logout_smtp.return_value = None

        result = MailProcessor.validate_smtp_connection('test_bot_id')

        assert  result

        mock_login_smtp.assert_called_once()
        mock_logout_smtp.assert_called_once()

    @patch('kairon.shared.channels.mail.processor.MailProcessor.login_smtp')
    @patch('kairon.shared.channels.mail.processor.MailProcessor.logout_smtp')
    def test_validate_smpt_connection_failure(self, mock_logout_smtp, mock_login_smtp):
        mock_login_smtp.side_effect = Exception("SMTP login failed")

        result = MailProcessor.validate_smtp_connection('test_bot_id')

        assert not result

    @patch('kairon.shared.channels.mail.processor.MailProcessor.__init__')
    @patch('kairon.shared.channels.mail.processor.MailProcessor.login_imap')
    @patch('kairon.shared.channels.mail.processor.MailProcessor.logout_imap')
    def test_validate_imap_connection(self, mp, mock_logout_imap, mock_login_imap):
        mp.return_value = None
        mock_login_imap.return_value = None
        mock_logout_imap.return_value = None

        result = MailProcessor.validate_imap_connection('test_bot_id')

        assert result

        mock_login_imap.assert_called_once()
        mock_logout_imap.assert_called_once()

    @patch('kairon.shared.channels.mail.processor.MailProcessor.login_imap')
    @patch('kairon.shared.channels.mail.processor.MailProcessor.logout_imap')
    def test_validate_imap_connection_failure(self, mock_logout_imap, mock_login_imap):
        mock_login_imap.side_effect = Exception("imap login failed")

        result = MailProcessor.validate_imap_connection('test_bot_id')

        assert not result

    def test_get_mail_channel_state_data_existing_state(self):
        bot_id = self.bot_id
        mock_state = MagicMock()

        with patch.object(MailChannelStateData, 'objects') as mock_objects:
            mock_objects.return_value.first.return_value = mock_state
            result = MailProcessor.get_mail_channel_state_data(bot_id)

            assert result == mock_state
            mock_objects.return_value.first.assert_called_once()

    def test_get_mail_channel_state_data_new_state(self):
        bot_id = self.bot_id
        mock_state = MagicMock()
        mock_state.bot = bot_id
        mock_state.state = "some_state"
        mock_state.timestamp = "some_timestamp"

        with patch.object(MailChannelStateData, 'objects') as mock_objects:
            mock_objects.return_value.first.return_value = None
            with patch.object(MailChannelStateData, 'save', return_value=None) as mock_save:
                with patch('kairon.shared.channels.mail.data_objects.MailChannelStateData', return_value=mock_state):
                    result = MailProcessor.get_mail_channel_state_data(bot_id)

                    assert result.bot == mock_state.bot


    def test_get_mail_channel_state_data_exception(self):
        bot_id = "test_bot"

        with patch.object(MailChannelStateData, 'objects') as mock_objects:
            mock_objects.side_effect = Exception("Test Exception")
            with pytest.raises(AppException) as excinfo:
                MailProcessor.get_mail_channel_state_data(bot_id)

            assert str(excinfo.value) == "Test Exception"


    def test_get_log(self):
        bot_id = "test_bot"
        offset = 0
        limit = 10

        mock_log = MagicMock()
        mock_log.to_mongo.return_value.to_dict.return_value = {
            '_id': 'some_id',
            'bot': bot_id,
            'user': 'test_user',
            'timestamp': 1234567890,
            'subject': 'Test Subject',
            'body': 'Test Body',
            'status': MailStatus.SUCCESS.value
        }

        with patch.object(MailResponseLog, 'objects') as mock_objects:
            mock_objects.return_value.count.return_value = 1
            mock_objects.return_value.order_by.return_value.skip.return_value.limit.return_value = [mock_log]

            result = MailProcessor.get_log(bot_id, offset, limit)

            assert result['count'] == 1
            assert len(result['logs']) == 1
            assert result['logs'][0]['timestamp'] == 1234567890
            assert result['logs'][0]['subject'] == 'Test Subject'
            assert result['logs'][0]['body'] == 'Test Body'
            assert result['logs'][0]['status'] == MailStatus.SUCCESS.value

    def test_get_log_exception(self):
        bot_id = "test_bot"
        offset = 0
        limit = 10

        with patch.object(MailResponseLog, 'objects') as mock_objects:
            mock_objects.side_effect = Exception("Test Exception")

            with pytest.raises(AppException) as excinfo:
                MailProcessor.get_log(bot_id, offset, limit)

            assert str(excinfo.value) == "Test Exception"



    @pytest.fixture
    def config_dict(self):
        return {
            'email_account': 'test@example.com',
            'subjects': 'subject1,subject2'
        }

    @patch('kairon.shared.chat.processor.ChatDataProcessor.get_all_channel_configs')
    def test_check_email_config_exists_no_existing_config(self,mock_get_all_channel_configs, config_dict):
        mock_get_all_channel_configs.return_value = []
        result = MailProcessor.check_email_config_exists('test', config_dict)
        assert result == False

    @patch('kairon.shared.chat.processor.ChatDataProcessor.get_all_channel_configs')
    def test_check_email_config_exists_same_config_exists(self, mock_get_all_channel_configs, config_dict):
        mock_get_all_channel_configs.return_value = [{
            'bot': 'test',
            'config': config_dict
        }]
        result = MailProcessor.check_email_config_exists('test_bot', config_dict)
        assert result == True

    @patch('kairon.shared.chat.processor.ChatDataProcessor.get_all_channel_configs')
    def test_check_email_config_exists_different_config_exists(self,mock_get_all_channel_configs, config_dict):
        existing_config = config_dict.copy()
        existing_config['subjects'] = 'subject3'
        mock_get_all_channel_configs.return_value = [{
            "bot": 'test_bot',
            'config': existing_config
        }]
        result = MailProcessor.check_email_config_exists('test', config_dict)
        assert result == False

    @patch('kairon.shared.chat.processor.ChatDataProcessor.get_all_channel_configs')
    def test_check_email_config_exists_ignore_same_bot(self, mock_get_all_channel_configs, config_dict):
        existing_config = config_dict.copy()
        mock_get_all_channel_configs.return_value = [{
            "bot": 'test_bot',
            'config': existing_config
        }]
        result = MailProcessor.check_email_config_exists('test_bot', config_dict)
        assert result == False

    @patch('kairon.shared.chat.processor.ChatDataProcessor.get_all_channel_configs')
    def test_check_email_config_exists_partial_subject_match(self, mock_get_all_channel_configs, config_dict):
        existing_config = config_dict.copy()
        existing_config['subjects'] = 'subject1,subject3'
        mock_get_all_channel_configs.return_value = [{
            'bot': 'test_bot',
            'config': existing_config
        }]
        result = MailProcessor.check_email_config_exists('test', config_dict)
        assert result == True

    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail_with_cc(self, mock_get_channel_config, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance
        mail_response_log = MailResponseLog(bot=self.bot_id, sender_id="cc_recipient@test.com",
                                            user="mail_channel_test_user_acc", uid=300)
        mail_response_log.save()
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }
        mp = MailProcessor(bot=self.bot_id)
        mp.login_smtp()
        await mp.send_mail("cc_recipient@test.com", "CC Subject", "CC Body", mail_response_log.id,
                           cc=["cc1@example.com", "cc2@example.com"])
        mock_smtp_instance.sendmail.assert_called_once()
        call_args = mock_smtp_instance.sendmail.call_args[0]
        assert call_args[1] == ["cc_recipient@test.com", "cc1@example.com", "cc2@example.com"]
        assert "cc1@example.com" in call_args[2]
        MailResponseLog.objects().delete()

    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail_with_message_id(self, mock_get_channel_config, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance
        mail_response_log = MailResponseLog(bot=self.bot_id, sender_id="thread_recipient@test.com",
                                            user="mail_channel_test_user_acc", uid=301)
        mail_response_log.save()
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }
        mp = MailProcessor(bot=self.bot_id)
        mp.login_smtp()
        original_msg_id = "<original123@testserver.com>"
        await mp.send_mail("thread_recipient@test.com", "Re: Thread", "Reply body", mail_response_log.id,
                           message_id=original_msg_id)
        mock_smtp_instance.sendmail.assert_called_once()
        msg_str = mock_smtp_instance.sendmail.call_args[0][2]
        assert "In-Reply-To:" in msg_str
        assert "References:" in msg_str
        assert original_msg_id in msg_str
        MailResponseLog.objects().delete()

    @patch("kairon.shared.chat.user_media.UserMedia.save_media_content")
    @patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_with_attachment_success(self, mock_get_channel_config,
                                                       mock_mailbox, mock_process_message_task,
                                                       mock_logout_imap,
                                                       mock_create_media, mock_save_media):
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_att = MagicMock()
        mock_att.filename = "document.pdf"
        mock_att.payload = b"pdf_content"

        mock_mail_message = MagicMock(spec=MailMessage)
        mock_mail_message.subject = "Attachment Mail"
        mock_mail_message.from_ = "sender@example.com"
        mock_mail_message.date = "2024-01-15"
        mock_mail_message.text = "Mail with attachment"
        mock_mail_message.uid = "99100"
        mock_mail_message.html = None
        mock_mail_message.attachments = [mock_att]
        mock_mail_message.headers = MagicMock()
        mock_mail_message.headers.get.side_effect = lambda key, default=None: \
            ['<att-test@example.com>'] if key == 'message-id' else (default or [])

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [mock_mail_message]

        mails, user = MailProcessor.read_mails(bot_id)

        assert len(mails) == 1
        assert len(mails[0]["media_ids"]) == 1
        mock_create_media.assert_called_once()
        mock_save_media.assert_called_once()
        save_kwargs = mock_save_media.call_args[1]
        assert save_kwargs.get("is_validation_required") is True
        assert ".pdf" in save_kwargs.get("allowed_extensions", [])
        MailResponseLog.objects().delete()

    @patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_with_attachment_failure(self, mock_get_channel_config,
                                                       mock_mailbox, mock_process_message_task,
                                                       mock_logout_imap, mock_create_media):
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_att = MagicMock()
        mock_att.filename = "broken.pdf"
        mock_att.payload = b"data"

        mock_mail_message = MagicMock(spec=MailMessage)
        mock_mail_message.subject = "Failing Attachment"
        mock_mail_message.from_ = "fail@example.com"
        mock_mail_message.date = "2024-01-15"
        mock_mail_message.text = "Body"
        mock_mail_message.uid = "99200"
        mock_mail_message.html = None
        mock_mail_message.attachments = [mock_att]
        mock_mail_message.headers = MagicMock()
        mock_mail_message.headers.get.side_effect = lambda key, default=None: \
            ['<att-fail@example.com>'] if key == 'message-id' else (default or [])

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [mock_mail_message]
        mock_create_media.side_effect = Exception("Storage unavailable")

        mails, user = MailProcessor.read_mails(bot_id)

        assert len(mails) == 1
        assert mails[0]["media_ids"] == []
        log = MailResponseLog.objects(bot=bot_id).order_by('-timestamp').first()
        assert log is not None
        assert "broken.pdf" in log.failed_attachments
        MailResponseLog.objects().delete()

    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.login_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.send_mail")
    @patch("kairon.shared.chat.agent.agent_flow.AgenticFlow.execute_rule")
    @pytest.mark.asyncio
    async def test_process_messages_with_cc_and_message_id(self, mock_execute_rule, mock_send_mail,
                                                            mock_logout_smtp, mock_login_smtp,
                                                            mock_get_channel_config):
        mail_response_log = MailResponseLog(bot=self.bot_id, sender_id="cc_test@test.com",
                                            user="mail_channel_test_user_acc", uid=302)
        mail_response_log.save()
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        batch = [{
            "mail_id": "cc_test@test.com",
            "subject": "CC Subject",
            "date": "2024-01-15",
            "body": "Body",
            "log_id": str(mail_response_log.id),
            "cc": ["cc@example.com"],
            "message_id": "<original@test.com>"
        }]
        mock_execute_rule.return_value = [{"text": "Response"}], []
        await MailProcessor.process_messages(self.bot_id, batch)
        mock_send_mail.assert_called_once()
        send_kwargs = mock_send_mail.call_args[1]
        assert send_kwargs.get("cc") == ["cc@example.com"]
        assert send_kwargs.get("message_id") == "<original@test.com>"
        MailResponseLog.objects().delete()

    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.login_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.send_mail")
    @patch("kairon.shared.chat.agent.agent_flow.AgenticFlow.execute_rule")
    @pytest.mark.asyncio
    async def test_process_messages_passes_followup_slots(self, mock_execute_rule, mock_send_mail,
                                                          mock_logout_smtp, mock_login_smtp,
                                                          mock_get_channel_config):
        """is_followup and parent_log_id must be forwarded to execute_rule as slot_vals."""
        mail_response_log = MailResponseLog(bot=self.bot_id, sender_id="followup@test.com",
                                            user="mail_channel_test_user_acc", uid=303)
        mail_response_log.save()
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        parent_id = str(mail_response_log.id)
        batch = [{
            "mail_id": "followup@test.com",
            "subject": "Re: Original",
            "date": "2024-01-15",
            "body": "Body",
            "log_id": str(mail_response_log.id),
            "cc": [],
            "message_id": "<reply@test.com>",
            "is_followup": True,
            "parent_log_id": parent_id,
        }]
        mock_execute_rule.return_value = [{"text": "Response"}], []
        await MailProcessor.process_messages(self.bot_id, batch)
        call_kwargs = mock_execute_rule.call_args[1]
        slot_vals = call_kwargs.get("slot_vals", {})
        assert slot_vals.get("is_followup") is True
        assert slot_vals.get("parent_log_id") == parent_id
        MailResponseLog.objects().delete()

    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    def test_update_event_id(self, mock_get_channel_config):
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_state = MagicMock()
        mock_state.event_id = None
        with patch.object(MailProcessor, 'get_mail_channel_state_data', return_value=mock_state):
            mp = MailProcessor(bot=self.bot_id)
            mp.update_event_id("evt_abc123")
        assert mock_state.event_id == "evt_abc123"
        mock_state.save.assert_called_once()

    @patch("asyncio.run")
    def test_process_message_task(self, mock_run):
        batch = [{"mail_id": "t@t.com", "subject": "S", "date": "d", "body": "b"}]
        MailProcessor.process_message_task(self.bot_id, batch)
        mock_run.assert_called_once()

    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail_filters_self_from_cc(self, mock_get_channel_config, mock_smtp):
        """Bot's own email in CC must be excluded from recipients to prevent self-reply loop."""
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance
        mail_response_log = MailResponseLog(bot=self.bot_id, sender_id="recipient@test.com",
                                            user="mail_channel_test_user_acc", uid=400)
        mail_response_log.save()
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }
        mp = MailProcessor(bot=self.bot_id)
        mp.login_smtp()
        await mp.send_mail(
            "recipient@test.com", "Subject", "Body", mail_response_log.id,
            cc=["cc1@example.com", "mail_channel_test_user_acc@testuser.com", "cc2@example.com"]
        )
        call_args = mock_smtp_instance.sendmail.call_args[0]
        assert "mail_channel_test_user_acc@testuser.com" not in call_args[1]
        assert "cc1@example.com" in call_args[1]
        assert "cc2@example.com" in call_args[1]
        MailResponseLog.objects().delete()

    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_skips_self_sent(self, mock_get_channel_config, mock_mailbox,
                                              mock_process_message_task, mock_logout_imap):
        """Emails where sender == bot email_account must be skipped."""
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_self_mail = MagicMock(spec=MailMessage)
        mock_self_mail.subject = "Bot's own reply"
        mock_self_mail.from_ = "mail_channel_test_user_acc@testuser.com"
        mock_self_mail.date = "2024-01-15"
        mock_self_mail.text = "Reply body"
        mock_self_mail.uid = "99300"
        mock_self_mail.html = None
        mock_self_mail.attachments = []
        mock_self_mail.headers = MagicMock()
        mock_self_mail.headers.get.side_effect = lambda key, default=None: default or []

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [mock_self_mail]

        mails, user = MailProcessor.read_mails(bot_id)
        assert len(mails) == 0

    @patch("kairon.shared.chat.user_media.UserMedia.save_media_content")
    @patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_disallowed_attachment_skipped(self, mock_get_channel_config,
                                                             mock_mailbox, mock_process_message_task,
                                                             mock_logout_imap, mock_create_media,
                                                             mock_save_media):
        """Attachments with extensions not in mail allowlist must be skipped."""
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_att = MagicMock()
        mock_att.filename = "malware.exe"
        mock_att.payload = b"binary"

        mock_mail_message = MagicMock(spec=MailMessage)
        mock_mail_message.subject = "Suspicious Mail"
        mock_mail_message.from_ = "attacker@example.com"
        mock_mail_message.date = "2024-01-15"
        mock_mail_message.text = "Body"
        mock_mail_message.uid = "99400"
        mock_mail_message.html = None
        mock_mail_message.attachments = [mock_att]
        mock_mail_message.headers = MagicMock()
        mock_mail_message.headers.get.side_effect = lambda key, default=None: \
            ['<disallowed-att@example.com>'] if key == 'message-id' else (default or [])

        mock_save_media.side_effect = Exception("Only [...] type files allowed")
        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [mock_mail_message]

        mails, user = MailProcessor.read_mails(bot_id)

        assert len(mails) == 1
        assert mails[0]["media_ids"] == []
        mock_create_media.assert_called_once()
        mock_save_media.assert_called_once()
        log = MailResponseLog.objects(bot=bot_id).order_by('-timestamp').first()
        assert "malware.exe" in log.failed_attachments
        MailResponseLog.objects().delete()

    @patch("kairon.shared.chat.user_media.UserMedia.save_media_content")
    @patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_followup_detection(self, mock_get_channel_config, mock_mailbox,
                                                  mock_process_message_task, mock_logout_imap,
                                                  mock_create_media, mock_save_media):
        """Reply email with In-Reply-To matching an existing log must have is_followup=True."""
        bot_id = self.bot_id
        original_msg_id = "<original-thread-id@testserver.com>"
        parent_log = MailResponseLog(
            bot=bot_id,
            sender_id="user@company.com",
            user="mail_channel_test_user",
            uid=88000,
            message_id=original_msg_id
        )
        parent_log.save()

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_reply = MagicMock(spec=MailMessage)
        mock_reply.subject = "Re: Original Subject"
        mock_reply.from_ = "spoc@company.com"
        mock_reply.date = "2024-01-16"
        mock_reply.text = "Reply body"
        mock_reply.uid = "99500"
        mock_reply.html = None
        mock_reply.attachments = []
        mock_reply.headers = MagicMock()
        mock_reply.headers.get.side_effect = lambda key, default=None: {
            'message-id': ['<reply-msg-id@testserver.com>'],
            'in-reply-to': [original_msg_id],
        }.get(key, default or [])

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [mock_reply]

        mails, user = MailProcessor.read_mails(bot_id)

        assert len(mails) == 1
        assert mails[0]["is_followup"] is True
        assert mails[0]["parent_log_id"] == str(parent_log.id)
        MailResponseLog.objects().delete()

    # ------------------------------------------------------------------ #
    # Realistic end-to-end scenarios                                       #
    # ------------------------------------------------------------------ #

    @patch("kairon.shared.chat.user_media.UserMedia.save_media_content")
    @patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_full_thread_lifecycle(self, mock_get_channel_config, mock_mailbox,
                                         mock_process_task, mock_logout,
                                         mock_create_media, mock_save_media):
        """
        S1: 4 emails in one fetch — original, two replies, bot's own mail.
        Only 3 user emails returned; bot mail skipped; thread linkage correct.
        """
        bot_id = self.bot_id
        bot_email = "mail_channel_test_user_acc@testuser.com"
        original_msg_id = "<original-s1@testserver.com>"

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': bot_email,
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        def make_msg(uid, from_, msg_id, in_reply_to=None):
            m = MagicMock(spec=MailMessage)
            m.uid = str(uid)
            m.from_ = from_
            m.subject = "Support Request"
            m.date = "2024-06-01"
            m.text = f"Message from {from_}"
            m.html = None
            m.attachments = []
            m.cc = []
            headers = {'message-id': [msg_id]}
            if in_reply_to:
                headers['in-reply-to'] = [in_reply_to]
            m.headers = MagicMock()
            m.headers.get.side_effect = lambda k, d=None: headers.get(k, d or [])
            return m

        msgs = [
            make_msg(100200, "user@company.com",   original_msg_id),
            make_msg(100201, "spoc@company.com",   "<reply1-s1@testserver.com>", in_reply_to=original_msg_id),
            make_msg(100202, "mgr@company.com",    "<reply2-s1@testserver.com>", in_reply_to=original_msg_id),
            make_msg(100203, bot_email,             "<bot-sent-s1@testserver.com>"),
        ]
        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = msgs

        mails, user = MailProcessor.read_mails(bot_id)

        assert len(mails) == 3, "Bot's own mail must be skipped"

        original_log = MailResponseLog.objects(bot=bot_id, uid=100200).first()
        assert original_log is not None

        assert mails[0]["is_followup"] is False
        assert mails[0]["parent_log_id"] is None

        assert mails[1]["is_followup"] is True
        assert mails[1]["parent_log_id"] == str(original_log.id)

        assert mails[2]["is_followup"] is True
        assert mails[2]["parent_log_id"] == str(original_log.id)

        MailResponseLog.objects(bot=bot_id).delete()

    @patch("kairon.shared.chat.user_media.UserMedia.save_media_content")
    @patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_mixed_attachments(self, mock_get_channel_config, mock_mailbox,
                                                 mock_process_task, mock_logout,
                                                 mock_create_media, mock_save_media):
        """
        S2: Email with 3 attachments — allowed .pdf, disallowed .exe, allowed .xlsx.
        save_media_content rejects .exe (raises); pdf and xlsx stored, exe in failed_attachments.
        """
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        def make_att(filename):
            a = MagicMock()
            a.filename = filename
            a.payload = b"data"
            return a

        msg = MagicMock(spec=MailMessage)
        msg.uid = "100600"
        msg.from_ = "sender@company.com"
        msg.subject = "Mixed attachments"
        msg.date = "2024-06-01"
        msg.text = "See attached"
        msg.html = None
        msg.cc = []
        msg.attachments = [make_att("report.pdf"), make_att("malware.exe"), make_att("data.xlsx")]
        msg.headers = MagicMock()
        msg.headers.get.side_effect = lambda k, d=None: \
            ['<mixed-att@testserver.com>'] if k == 'message-id' else (d or [])

        # 2nd save_media_content call (malware.exe) raises — simulates UserMedia rejecting it
        save_call = {"n": 0}
        def save_side_effect(*args, **kwargs):
            save_call["n"] += 1
            if save_call["n"] == 2:
                raise Exception("Only [...] type files allowed")
        mock_save_media.side_effect = save_side_effect

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [msg]

        mails, _ = MailProcessor.read_mails(bot_id)

        assert len(mails) == 1
        assert len(mails[0]["media_ids"]) == 2, "pdf and xlsx stored; exe rejected by UserMedia"
        assert mock_create_media.call_count == 3, "create called for all 3 before save rejects"
        assert mock_save_media.call_count == 3
        log = MailResponseLog.objects(bot=bot_id, uid=100600).first()
        assert "malware.exe" in log.failed_attachments
        assert log.failed_attachments == ["malware.exe"]
        MailResponseLog.objects(bot=bot_id).delete()

    @patch("kairon.shared.chat.user_media.UserMedia.save_media_content")
    @patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_partial_attachment_failure(self, mock_get_channel_config, mock_mailbox,
                                                          mock_process_task, mock_logout,
                                                          mock_create_media, mock_save_media):
        """
        S3: 2 PDFs — upload succeeds for first, raises on second.
        First in media_ids; second in failed_attachments. UID advances.
        """
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        call_count = {"n": 0}
        def save_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise Exception("S3 upload failed")
        mock_save_media.side_effect = save_side_effect

        def make_att(filename):
            a = MagicMock()
            a.filename = filename
            a.payload = b"data"
            return a

        msg = MagicMock(spec=MailMessage)
        msg.uid = "100700"
        msg.from_ = "sender@company.com"
        msg.subject = "Partial failure"
        msg.date = "2024-06-01"
        msg.text = "Two PDFs attached"
        msg.html = None
        msg.cc = []
        msg.attachments = [make_att("good.pdf"), make_att("bad.pdf")]
        msg.headers = MagicMock()
        msg.headers.get.side_effect = lambda k, d=None: \
            ['<partial-fail@testserver.com>'] if k == 'message-id' else (d or [])

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [msg]

        mails, _ = MailProcessor.read_mails(bot_id)

        assert len(mails) == 1
        assert len(mails[0]["media_ids"]) == 1
        log = MailResponseLog.objects(bot=bot_id, uid=100700).first()
        assert "bad.pdf" in log.failed_attachments
        assert "good.pdf" not in log.failed_attachments
        state = MailChannelStateData.objects(bot=bot_id).first()
        assert state.last_email_uid == 100700
        MailResponseLog.objects(bot=bot_id).delete()

    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail_cc_only_self_filtered(self, mock_get_channel_config, mock_smtp):
        """
        S4: CC list contains only the bot's own address.
        After filtering, CC header must be absent and recipients = [to] only.
        """
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance
        bot_email = "mail_channel_test_user_acc@testuser.com"
        log = MailResponseLog(bot=self.bot_id, sender_id="user@test.com",
                              user="mail_channel_test_user_acc", uid=500)
        log.save()
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': bot_email,
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }
        mp = MailProcessor(bot=self.bot_id)
        mp.login_smtp()
        await mp.send_mail("user@test.com", "Subject", "Body", log.id,
                           cc=[bot_email])

        call_args = mock_smtp_instance.sendmail.call_args[0]
        assert call_args[1] == ["user@test.com"], "Only To, no CC when self is only CC member"
        from email import message_from_string
        parsed = message_from_string(call_args[2])
        assert parsed['CC'] is None, "CC header must be absent"
        MailResponseLog.objects().delete()

    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_uid_state_advancement(self, mock_get_channel_config, mock_mailbox,
                                                     mock_process_task, mock_logout):
        """
        S5: last_processed_uid=100. Fetch returns UIDs 99, 101, 102.
        UID 99 skipped; 101 and 102 processed; state saved as 102.
        """
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        state = MailChannelStateData.objects(bot=bot_id).first()
        if not state:
            state = MailChannelStateData(bot=bot_id)
        state.last_email_uid = 100
        state.save()

        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        def make_msg(uid):
            m = MagicMock(spec=MailMessage)
            m.uid = str(uid)
            m.from_ = f"user{uid}@example.com"
            m.subject = f"Email {uid}"
            m.date = "2024-06-01"
            m.text = "Body"
            m.html = None
            m.cc = []
            m.attachments = []
            m.headers = MagicMock()
            m.headers.get.side_effect = lambda k, d=None: \
                [f'<msg-{uid}@testserver.com>'] if k == 'message-id' else (d or [])
            return m

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [make_msg(99), make_msg(101), make_msg(102)]

        mails, _ = MailProcessor.read_mails(bot_id)

        assert len(mails) == 2, "UID 99 must be skipped"
        assert mails[0]["mail_id"] == "user101@example.com"
        assert mails[1]["mail_id"] == "user102@example.com"
        updated_state = MailChannelStateData.objects(bot=bot_id).first()
        assert updated_state.last_email_uid == 102
        MailResponseLog.objects(bot=bot_id).delete()

    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_body_fallback(self, mock_get_channel_config, mock_mailbox,
                                             mock_process_task, mock_logout):
        """
        S6: text+HTML → text wins; HTML-only → HTML used; no body → empty string.
        """
        bot_id = self.bot_id
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
            }
        }
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        def make_msg(uid, text, html):
            m = MagicMock(spec=MailMessage)
            m.uid = str(uid)
            m.from_ = f"u{uid}@example.com"
            m.subject = "Body test"
            m.date = "2024-06-01"
            m.text = text
            m.html = html
            m.cc = []
            m.attachments = []
            m.headers = MagicMock()
            m.headers.get.side_effect = lambda k, d=None: \
                [f'<body-{uid}@test.com>'] if k == 'message-id' else (d or [])
            return m

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [
            make_msg(1001, "plain text", "<b>HTML</b>"),
            make_msg(1002, None,         "<b>HTML only</b>"),
            make_msg(1003, None,         None),
        ]

        mails, _ = MailProcessor.read_mails(bot_id)

        assert len(mails) == 3
        assert mails[0]["body"] == "plain text",    "text takes priority over html"
        assert mails[1]["body"] == "<b>HTML only</b>", "html used when no text"
        assert mails[2]["body"] == "",              "empty string when no body"
        MailResponseLog.objects(bot=bot_id).delete()

    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail_cc_self_filter_case_insensitive(self, mock_get_channel_config, mock_smtp):
        """
        S7: Bot email configured as mixed-case. CC contains lowercase variant.
        Must still be filtered out (case-insensitive match).
        """
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance
        log = MailResponseLog(bot=self.bot_id, sender_id="user@test.com",
                              user="mail_channel_test_user_acc", uid=600)
        log.save()
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "Bot@Test.COM",
                'email_password': "password",
                'smtp_server': "smtp.testuser.com",
                'smtp_port': 587
            }
        }
        mp = MailProcessor(bot=self.bot_id)
        mp.login_smtp()
        await mp.send_mail("user@test.com", "Subject", "Body", log.id,
                           cc=["bot@test.com", "other@example.com"])

        call_args = mock_smtp_instance.sendmail.call_args[0]
        assert "bot@test.com" not in call_args[1], "case-insensitive self must be filtered"
        assert "other@example.com" in call_args[1]
        MailResponseLog.objects().delete()
