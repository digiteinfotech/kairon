import os
from unittest.mock import patch, MagicMock

import pytest
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
    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        a = Account.objects.create(name="mail_channel_test_user_acc", user="mail_channel_test_user_acc")
        bot = Bot.objects.create(name="mail_channel_test_bot", user="mail_channel_test_user_acc", status=True,
                                 account=a.id)
        pytest.mail_test_bot = str(bot.id)
        BotSettings(bot=pytest.mail_test_bot, user="mail_channel_test_user_acc").save()
        yield

        BotSettings.objects(user="mail_channel_test_user_acc").delete()
        Bot.objects(user="mail_channel_test_user_acc").delete()
        Account.objects(user="mail_channel_test_user_acc").delete()
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

        bot_id = pytest.mail_test_bot
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

        bot_id = pytest.mail_test_bot
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

        bot_id = pytest.mail_test_bot
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

        bot_id = pytest.mail_test_bot
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

        mail_response_log = MailResponseLog(bot=pytest.mail_test_bot,
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
        bot_id = pytest.mail_test_bot
        mp = MailProcessor(bot=bot_id)
        mp.login_smtp()

        await mp.send_mail("recipient@test.com", "Test Subject", "Test Body", mail_response_log.id)

        MailResponseLog.objects().delete()

        mock_smtp_instance.sendmail.assert_called_once()
        assert mock_smtp_instance.sendmail.call_args[0][0] == "mail_channel_test_user_acc@testuser.com"
        assert mock_smtp_instance.sendmail.call_args[0][1] == "recipient@test.com"
        assert "Test Subject" in mock_smtp_instance.sendmail.call_args[0][2]
        assert "Test Body" in mock_smtp_instance.sendmail.call_args[0][2]

    @patch("kairon.shared.channels.mail.processor.smtplib.SMTP")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail_exception(self, mock_get_channel_config, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mail_response_log = MailResponseLog(bot=pytest.mail_test_bot,
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

        bot_id = pytest.mail_test_bot
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

        mail_response_log = MailResponseLog(bot=pytest.mail_test_bot,
                                            sender_id="recipient@test.com",
                                            user="mail_channel_test_user_acc",
                                            uid=123
                                            )
        mail_response_log.save()

        bot_id = pytest.mail_test_bot
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
        bot_id = pytest.mail_test_bot
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



    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails(self, mock_get_channel_config,
                                  mock_mailbox, mock_process_message_task,
                                 mock_logout_imap):
        bot_id = pytest.mail_test_bot

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

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = [mock_mail_message]

        mails, user = MailProcessor.read_mails(bot_id)
        print(mails)
        assert len(mails) == 1
        assert mails[0]["subject"] == "Test Subject"
        assert mails[0]["mail_id"] == "test@example.com"
        assert mails[0]["date"] == "2023-10-10"
        assert mails[0]["body"] == "Test Body"
        assert user == 'mail_channel_test_user_acc'




    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_read_mails_no_messages(self, mock_get_channel_config,
                                              mock_mailbox, mock_process_message_task,
                                             mock_logout_imap):
        bot_id = pytest.mail_test_bot

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
        assert user == 'mail_channel_test_user_acc'

        mock_logout_imap.assert_called_once()



    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.login_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_smtp")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.send_mail")
    @patch("kairon.shared.chat.agent.agent_flow.AgenticFlow.execute_rule")
    @pytest.mark.asyncio
    async def test_process_messages(self, mock_process_messages_via_bot, mock_send_mail, mock_logout_smtp, mock_login_smtp, mock_get_channel_config):

        mail_response_log = MailResponseLog(bot=pytest.mail_test_bot,
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

        bot = pytest.mail_test_bot
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
        bot_id = pytest.mail_test_bot
        mock_state = MagicMock()

        with patch.object(MailChannelStateData, 'objects') as mock_objects:
            mock_objects.return_value.first.return_value = mock_state
            result = MailProcessor.get_mail_channel_state_data(bot_id)

            assert result == mock_state
            mock_objects.return_value.first.assert_called_once()

    def test_get_mail_channel_state_data_new_state(self):
        bot_id = pytest.mail_test_bot
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

        BotSettings.objects(user="mail_channel_test_user_acc").delete()
        Bot.objects(user="mail_channel_test_user_acc").delete()
        Account.objects(user="mail_channel_test_user_acc").delete()
        Channels.objects(connector_type=ChannelTypes.MAIL.value).delete()



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
