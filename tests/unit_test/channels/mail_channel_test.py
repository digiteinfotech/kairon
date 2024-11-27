import asyncio
import os
from unittest.mock import patch, MagicMock

import pytest
from imap_tools import MailMessage

from mongoengine import connect, disconnect

from kairon import Utility
os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from kairon.shared.account.data_objects import Bot, Account
from kairon.shared.channels.mail.constants import MailConstants
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.chat.data_objects import Channels
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.data.data_objects import BotSettings

from kairon.shared.channels.mail.data_objects import MailClassificationConfig
from kairon.exceptions import AppException
from kairon.shared.constants import ChannelTypes



class TestMailChannel:
    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

        yield

        self.remove_basic_data()
        disconnect()

    def create_basic_data(self):
        a = Account.objects.create(name="mail_channel_test_user_acc", user="mail_channel_test_user_acc")
        bot = Bot.objects.create(name="mail_channel_test_bot", user="mail_channel_test_user_acc", status=True, account=a.id)
        pytest.mail_test_bot = str(bot.id)
        b = BotSettings.objects.create(bot=pytest.mail_test_bot, user="mail_channel_test_user_acc")
        # b.llm_settings.enable_faq = True
        b.save()
        ChatDataProcessor.save_channel_config(
            {
                "connector_type": ChannelTypes.MAIL.value,
                "config": {
                    'email_account': "mail_channel_test_user_acc@testuser.com",
                    'email_password': "password",
                    'imap_server': "imap.testuser.com",
                    'smtp_server': "smtp.testuser.com",
                    'smtp_port': "587",
                }
            },
            pytest.mail_test_bot,
            user="mail_channel_test_user_acc",
        )

    def remove_basic_data(self):
        MailClassificationConfig.objects.delete()
        BotSettings.objects(user="mail_channel_test_user_acc").delete()
        Bot.objects(user="mail_channel_test_user_acc").delete()
        Account.objects(user="mail_channel_test_user_acc").delete()
        Channels.objects(connector_type=ChannelTypes.MAIL.value).delete()

    def test_create_doc_new_entry(self):
        self.create_basic_data()
        print(pytest.mail_test_bot)
        doc = MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        assert doc.intent == "greeting"
        assert doc.bot == pytest.mail_test_bot
        assert doc.status is True
        MailClassificationConfig.objects.delete()



    def test_create_doc_existing_active_entry(self):
        MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        with pytest.raises(AppException, match=r"Mail configuration already exists for intent \[greeting\]"):
            MailClassificationConfig.create_doc(
                intent="greeting",
                entities=["user_email"],
                subjects=["hi"],
                classification_prompt="Another greeting.",
                reply_template="Hello!",
                bot=pytest.mail_test_bot,
                user="mail_channel_test_user_acc"
            )
        MailClassificationConfig.objects.delete()



    def test_get_docs(self):
        MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        MailClassificationConfig.create_doc(
            intent="goodbye",
            entities=["farewell"],
            subjects=["bye"],
            classification_prompt="Classify this email as a goodbye.",
            reply_template="Goodbye!",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        docs = MailClassificationConfig.get_docs(bot=pytest.mail_test_bot)
        assert len(docs) == 2
        assert docs[0]["intent"] == "greeting"
        assert docs[1]["intent"] == "goodbye"
        MailClassificationConfig.objects.delete()



    def test_get_doc(self):
        MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        doc = MailClassificationConfig.get_doc(bot=pytest.mail_test_bot, intent="greeting")
        assert doc["intent"] == "greeting"
        assert doc["classification_prompt"] == "Classify this email as a greeting."
        MailClassificationConfig.objects.delete()


    def test_get_doc_nonexistent(self):
        """Test retrieving a non-existent document."""
        with pytest.raises(AppException, match=r"Mail configuration does not exist for intent \[greeting\]"):
            MailClassificationConfig.get_doc(bot=pytest.mail_test_bot, intent="greeting")

        MailClassificationConfig.objects.delete()


    def test_delete_doc(self):
        """Test deleting a document."""
        MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        MailClassificationConfig.delete_doc(bot=pytest.mail_test_bot, intent="greeting")
        with pytest.raises(AppException, match=r"Mail configuration does not exist for intent \[greeting\]"):
            MailClassificationConfig.get_doc(bot=pytest.mail_test_bot, intent="greeting")

        MailClassificationConfig.objects.delete()


    def test_soft_delete_doc(self):
        MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        MailClassificationConfig.soft_delete_doc(bot=pytest.mail_test_bot, intent="greeting")
        with pytest.raises(AppException, match=r"Mail configuration does not exist for intent \[greeting\]"):
            MailClassificationConfig.get_doc(bot=pytest.mail_test_bot, intent="greeting")

        MailClassificationConfig.objects.delete()



    def test_update_doc(self):
        MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        MailClassificationConfig.update_doc(
            bot=pytest.mail_test_bot,
            intent="greeting",
            entities=["user_name", "greeting"],
            reply_template="Hello there!"
        )
        doc = MailClassificationConfig.get_doc(bot=pytest.mail_test_bot, intent="greeting")
        assert doc["entities"] == ["user_name", "greeting"]
        assert doc["reply_template"] == "Hello there!"

        MailClassificationConfig.objects.delete()

    def test_update_doc_invalid_key(self):
        MailClassificationConfig.create_doc(
            intent="greeting",
            entities=["user_name"],
            subjects=["hello"],
            classification_prompt="Classify this email as a greeting.",
            reply_template="Hi, how can I help?",
            bot=pytest.mail_test_bot,
            user="mail_channel_test_user_acc"
        )
        with pytest.raises(AppException, match=r"Invalid  key \[invalid_key\] provided for updating mail config"):
            MailClassificationConfig.update_doc(
                bot=pytest.mail_test_bot,
                intent="greeting",
                invalid_key="value"
            )

        MailClassificationConfig.objects.delete()


    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    def test_login_imap(self, mock_get_channel_config, mock_mailbox, mock_llm_processor):
        self.create_basic_data()
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance
        mock_mailbox_instance.login.return_value = ("OK", ["Logged in"])
        mock_mailbox_instance._simple_command.return_value = ("OK", ["Logged in"])
        mock_mailbox_instance.select.return_value = ("OK", ["INBOX"])

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

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
        mock_llm_processor.assert_called_once_with(bot_id, mp.llm_type)



    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    def test_login_imap_logout(self, mock_get_channel_config, mock_mailbox, mock_llm_processor):
        self.create_basic_data()
        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance
        mock_mailbox_instance.login.return_value = mock_mailbox_instance  # Ensure login returns the instance
        mock_mailbox_instance._simple_command.return_value = ("OK", ["Logged in"])
        mock_mailbox_instance.select.return_value = ("OK", ["INBOX"])

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

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
    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    def test_login_smtp(self, mock_get_channel_config, mock_llm_processor, mock_smtp):
        # Arrange
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

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
    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    def test_logout_smtp(self, mock_get_channel_config, mock_llm_processor, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

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
    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_send_mail(self, mock_get_channel_config, mock_llm_processor, mock_smtp):
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

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

        await mp.send_mail("recipient@test.com", "Test Subject", "Test Body")

        mock_smtp_instance.sendmail.assert_called_once()
        assert mock_smtp_instance.sendmail.call_args[0][0] == "mail_channel_test_user_acc@testuser.com"
        assert mock_smtp_instance.sendmail.call_args[0][1] == "recipient@test.com"
        assert "Test Subject" in mock_smtp_instance.sendmail.call_args[0][2]
        assert "Test Body" in mock_smtp_instance.sendmail.call_args[0][2]


    @patch("kairon.shared.channels.mail.processor.MailClassificationConfig")
    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.channels.mail.processor.ChatDataProcessor.get_channel_config")
    def test_process_mail(self,  mock_get_channel_config, llm_processor, mock_mail_classification_config):
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com"
            }
        }

        bot_id = pytest.mail_test_bot
        mp = MailProcessor(bot=bot_id)
        mp.mail_configs_dict = {
            "greeting": MagicMock(reply_template="Hello {name}, {bot_response}")
        }

        rasa_chat_response = {
            "slots": ["name: John Doe"],
            "response": [{"text": "How can I help you today?"}]
        }

        result = mp.process_mail("greeting", rasa_chat_response)

        assert result == "Hello John Doe, How can I help you today?"

        rasa_chat_response = {
            "slots": ["name: John Doe"],
            "response": [{"text": "How can I help you today?"}]
        }
        mp.mail_configs_dict = {}  # No template for the intent
        result = mp.process_mail("greeting", rasa_chat_response)
        assert result == MailConstants.DEFAULT_TEMPLATE.format(name="John Doe", bot_response="How can I help you today?")



    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.channels.mail.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.channels.mail.processor.BotSettings.objects")
    @patch("kairon.shared.channels.mail.processor.MailClassificationConfig.objects")
    @patch("kairon.shared.channels.mail.processor.Bot.objects")
    @pytest.mark.asyncio
    async def test_classify_messages(self, mock_bot_objects, mock_mail_classification_config_objects,
                                     mock_bot_settings_objects, mock_get_channel_config, mock_llm_processor):
        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
                'llm_type': "openai",
                'hyperparameters': MailConstants.DEFAULT_HYPERPARAMETERS,
                'system_prompt': "Test system prompt"
            }
        }

        mock_bot_settings = MagicMock()
        mock_bot_settings.llm_settings = {'enable_faq': True}
        mock_bot_settings_objects.get.return_value = mock_bot_settings

        mock_bot = MagicMock()
        mock_bot_objects.get.return_value = mock_bot

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

        future = asyncio.Future()
        future.set_result({"content": '[{"intent": "greeting", "entities": {"name": "John Doe"}, "mail_id": "123", "subject": "Hello"}]'})
        mock_llm_processor_instance.predict.return_value = future

        bot_id = pytest.mail_test_bot
        mp = MailProcessor(bot=bot_id)

        messages = [{"mail_id": "123", "subject": "Hello", "body": "Hi there"}]

        result = await mp.classify_messages(messages)

        assert result == [{"intent": "greeting", "entities": {"name": "John Doe"}, "mail_id": "123", "subject": "Hello"}]
        mock_llm_processor_instance.predict.assert_called_once()


    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    def test_get_context_prompt(self, llm_processor):
        bot_id = pytest.mail_test_bot
        mail_configs = [
            {
                'intent': 'greeting',
                'entities': 'name',
                'subjects': 'Hello',
                'classification_prompt': 'If the email says hello, classify it as greeting'
            },
            {
                'intent': 'farewell',
                'entities': 'name',
                'subjects': 'Goodbye',
                'classification_prompt': 'If the email says goodbye, classify it as farewell'
            }
        ]

        mp = MailProcessor(bot=bot_id)
        mp.mail_configs = mail_configs

        expected_context_prompt = (
            "intent: greeting \n"
            "entities: name \n"
            "\nclassification criteria: \n"
            "subjects: Hello \n"
            "rule: If the email says hello, classify it as greeting \n\n\n"
            "intent: farewell \n"
            "entities: name \n"
            "\nclassification criteria: \n"
            "subjects: Goodbye \n"
            "rule: If the email says goodbye, classify it as farewell \n\n\n"
        )

        context_prompt = mp.get_context_prompt()

        assert context_prompt == expected_context_prompt


    def test_extract_jsons_from_text(self):
        text = '''
        Here is some text with JSON objects.
        {"key1": "value1", "key2": "value2"}
        Some more text.
        [{"key3": "value3"}, {"key4": "value4"}]
        And some final text.
        '''
        expected_output = [
            {"key1": "value1", "key2": "value2"},
            [{"key3": "value3"}, {"key4": "value4"}]
        ]

        result = MailProcessor.extract_jsons_from_text(text)

        assert result == expected_output





    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.channels.mail.processor.BackgroundScheduler")
    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_process_mails(self, mock_get_channel_config, mock_llm_processor,
                                 mock_scheduler, mock_mailbox, mock_process_message_task,
                                 mock_logout_imap):
        bot_id = pytest.mail_test_bot

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
                'llm_type': "openai",
                'hyperparameters': MailConstants.DEFAULT_HYPERPARAMETERS,
            }
        }

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

        scheduler_instance = MagicMock()
        mock_scheduler.return_value = scheduler_instance

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

        message_count, time_shift = await MailProcessor.process_mails(bot_id)

        assert message_count == 1
        assert time_shift == 300  # 5 minutes in seconds



    @patch("kairon.shared.channels.mail.processor.MailProcessor.logout_imap")
    @patch("kairon.shared.channels.mail.processor.MailProcessor.process_message_task")
    @patch("kairon.shared.channels.mail.processor.MailBox")
    @patch("kairon.shared.channels.mail.processor.BackgroundScheduler")
    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_process_mails_no_messages(self, mock_get_channel_config, mock_llm_processor,
                                             mock_scheduler, mock_mailbox, mock_process_message_task,
                                             mock_logout_imap):
        bot_id = pytest.mail_test_bot

        mock_get_channel_config.return_value = {
            'config': {
                'email_account': "mail_channel_test_user_acc@testuser.com",
                'email_password': "password",
                'imap_server': "imap.testuser.com",
                'llm_type': "openai",
                'hyperparameters': MailConstants.DEFAULT_HYPERPARAMETERS,
            }
        }

        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

        scheduler_instance = MagicMock()
        mock_scheduler.return_value = scheduler_instance

        mock_mailbox_instance = MagicMock()
        mock_mailbox.return_value = mock_mailbox_instance

        mock_mailbox_instance.login.return_value = mock_mailbox_instance
        mock_mailbox_instance.fetch.return_value = []

        message_count, time_shift = await MailProcessor.process_mails(bot_id)

        assert message_count == 0
        assert time_shift == 300

        mock_logout_imap.assert_called_once()



    @patch("kairon.shared.channels.mail.processor.LLMProcessor")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @pytest.mark.asyncio
    async def test_classify_messages_invalid_llm_response(self, mock_get_channel_config, mock_llm_processor):
        mock_llm_processor_instance = MagicMock()
        mock_llm_processor.return_value = mock_llm_processor_instance

        future = asyncio.Future()
        future.set_result({"content": 'invalid json content'})
        mock_llm_processor_instance.predict.return_value = future

        mp = MailProcessor(bot=pytest.mail_test_bot)
        messages = [{"mail_id": "123", "subject": "Hello", "body": "Hi there"}]


        ans = await mp.classify_messages(messages)
        assert not ans










