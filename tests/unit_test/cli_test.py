import argparse
import os
from datetime import datetime
from unittest import mock

import pytest
from mongoengine import connect

from kairon import cli
from kairon.cli.conversations_deletion import initiate_history_deletion_archival
from kairon.cli.data_generator import generate_training_data
from kairon.cli.delete_logs import delete_logs
from kairon.cli.importer import validate_and_import
from kairon.cli.message_broadcast import send_notifications
from kairon.cli.testing import run_tests_on_model
from kairon.cli.training import train
from kairon.cli.translator import translate_multilingual_bot
from kairon.events.definitions.data_generator import DataGenerationEvent
from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import EventClass
from kairon.shared.utils import Utility


class TestTrainingCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]), alias="cli")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=train))
    def test_kairon_cli_train_no_arguments(self, monkeypatch):

        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=train, bot="test_cli"))
    def test_kairon_cli_train_no_argument_user(self, monkeypatch):
        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=train, bot="test_cli", user="testUser"))
    def test_kairon_cli_train(self, monkeypatch):
        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=train, bot="test_cli", user="testUser", token="test"))
    def test_kairon_cli_train_with_all_arguments(self, monkeypatch):
        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        cli()


class TestDataImporterCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import))
    def test_data_importer_no_arguments(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli"))
    def test_data_importer_no_user(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli", user="testUser",
                                                import_data=False, overwrite=False, event_type=EventClass.data_importer))
    def test_data_importer_with_defaults(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(TrainingDataImporterEvent, "execute", mock_data_importer)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli", user="testUser",
                                                import_data=True, overwrite=True, event_type=EventClass.data_importer))
    def test_data_importer_all_arguments(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(TrainingDataImporterEvent, "execute", mock_data_importer)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli", user="testUser",
                                                import_data=True, overwrite=False, event_type=EventClass.data_importer))
    def test_data_importer_with_all_args_overwrite_false(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(TrainingDataImporterEvent, "execute", mock_data_importer)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli", user="testUser",
                                                import_data="yes", overwrite=False, event_type=EventClass.data_importer))
    def test_data_importer_import_as_string_argument(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(TrainingDataImporterEvent, "execute", mock_data_importer)
        cli()


class TestModelTestingCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=run_tests_on_model))
    def test_kairon_cli_test_no_arguments(self, monkeypatch):

        def mock_testing(*args, **kwargs):
            return None

        monkeypatch.setattr(ModelTestingEvent, "execute", mock_testing)
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=run_tests_on_model, bot="test_cli"))
    def test_kairon_cli_test_no_argument_user(self, monkeypatch):
        def mock_testing(*args, **kwargs):
            return None

        monkeypatch.setattr(ModelTestingEvent, "execute", mock_testing)
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=run_tests_on_model, bot="test_cli", user="testUser", augment=False))
    def test_kairon_cli_test(self, monkeypatch):
        def mock_testing(*args, **kwargs):
            return None

        monkeypatch.setattr(ModelTestingEvent, "execute", mock_testing)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=run_tests_on_model, bot="test_cli", user="testUser", token="test", augment=True))
    def test_kairon_cli_test_with_all_arguments(self, monkeypatch):
        def mock_testing(*args, **kwargs):
            return None

        monkeypatch.setattr(ModelTestingEvent, "execute", mock_testing)
        cli()


class TestConversationsDeletionCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=initiate_history_deletion_archival))
    def test_cli_history_deletion_no_arguments(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=initiate_history_deletion_archival, bot="test_cli"))
    def test_cli_history_deletion_no_user(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=initiate_history_deletion_archival, bot="test_cli", user="testUser",
                                                sender_id=None, till_date=datetime.utcnow().date()))
    def test_cli_history_deletion_with_defaults(self, monkeypatch):
        def mock_history_delete(*args, **kwargs):
            return None

        monkeypatch.setattr(DeleteHistoryEvent, "execute", mock_history_delete)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=initiate_history_deletion_archival, bot="test_cli", user="testUser",
                                                sender_id='testSender', till_date=datetime.utcnow().date()))
    def test_cli_history_deletion_all_arguments(self, monkeypatch):
        def mock_history_delete(*args, **kwargs):
            return None

        monkeypatch.setattr(DeleteHistoryEvent, "execute", mock_history_delete)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=initiate_history_deletion_archival, bot="test_cli",
                                                user="testUser",
                                                sender_id='testSender', till_date="2022-02-14"))
    def test_cli_history_deletion_with_string_date(self, monkeypatch):
        def mock_history_delete(*args, **kwargs):
            return None

        monkeypatch.setattr(DeleteHistoryEvent, "execute", mock_history_delete)
        cli()


class TestMultilingualTranslatorCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=translate_multilingual_bot))
    def test_multilingual_translate_no_arguments(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=translate_multilingual_bot, bot="test_cli"))
    def test_multilingual_translate_no_user(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=translate_multilingual_bot, bot="test_cli", user="testUser",
                                                dest_lang="es", translate_responses=True, translate_actions=True))
    def test_multilingual_translate_all_arguments(self, monkeypatch):
        def mock_translator(*args, **kwargs):
            return None

        monkeypatch.setattr(MultilingualEvent, "execute", mock_translator)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=translate_multilingual_bot, bot="test_cli", user="testUser",
                                                dest_lang="es", translate_responses=False, translate_actions=False))
    def test_multilingual_translate_responses_and_actions_false(self, monkeypatch):
        def mock_translator(*args, **kwargs):
            return None

        monkeypatch.setattr(MultilingualEvent, "execute", mock_translator)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=translate_multilingual_bot, bot="test_cli", user="testUser",
                                                dest_lang="es", translate_responses="yes", translate_actions=False))
    def test_multilingual_translate_import_as_string_argument(self, monkeypatch):
        def mock_translator(*args, **kwargs):
            return None

        monkeypatch.setattr(MultilingualEvent, "execute", mock_translator)
        cli()


class TestDataGeneratorCli:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=generate_training_data))
    def test_data_generator_no_arguments(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=generate_training_data, bot="test_cli"))
    def test_data_generator_no_user(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=generate_training_data, bot="test_cli", user="testUser",
                                                path="test/website.com", from_website=True, depth=1))
    def test_data_generator_from_website(self, monkeypatch):
        def mock_generator(*args, **kwargs):
            return None

        monkeypatch.setattr(DataGenerationEvent, "execute", mock_generator)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=generate_training_data, bot="test_cli", user="testUser",
                                                path="test/website.com", from_document=True))
    def test_data_generator_from_document(self, monkeypatch):
        def mock_generator(*args, **kwargs):
            return None

        monkeypatch.setattr(DataGenerationEvent, "execute", mock_generator)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=generate_training_data, bot="test_cli", user="testUser",
                                                path="test/website.com", from_website="yes", depth=None))
    def test_data_generator_import_as_string_argument(self, monkeypatch):
        def mock_generator(*args, **kwargs):
            return None

        monkeypatch.setattr(DataGenerationEvent, "execute", mock_generator)
        cli()


class TestDeleteLogsCli:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @mock.patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(func=delete_logs))
    def test_delete_logs(self, mock_args):
        cli()


class TestMessageBroadcastCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=send_notifications))
    def test_message_broadcast_no_arguments(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=send_notifications, bot="test_cli"))
    def test_message_broadcast_no_user(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=send_notifications, bot="test_cli", user="testUser"))
    def test_message_broadcast_no_event_id(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'event_id'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=send_notifications, bot="test_cli", user="testUser",
                                                event_id="65432123456789876543"))
    def test_message_broadcast_no_is_resend(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'is_resend'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=send_notifications, bot="test_cli", user="testUser",
                                                event_id="65432123456789876543", is_resend="True"))
    def test_message_broadcast_all_arguments(self, mock_namespace):
        with mock.patch('kairon.events.definitions.message_broadcast.MessageBroadcastEvent.execute', autospec=True):

            cli()
        for proxy in ActorFactory._ActorFactory__actors.values():
            assert not proxy[1].actor_ref.is_alive()

    def test_message_broadcast_with_is_resend(self, monkeypatch):
        from kairon import create_argument_parser
        import sys

        test_args = ["kairon", "broadcast", "test_bot", "test_user", "65432123456789876543", "--is_resend", "True"]
        monkeypatch.setattr(sys, 'argv', test_args)

        parser = create_argument_parser()
        args = parser.parse_args()

        assert hasattr(args, 'is_resend')
        assert args.is_resend == "True"

        with mock.patch('kairon.events.definitions.message_broadcast.MessageBroadcastEvent.execute',
                        autospec=True):
            cli()

    def test_message_broadcast_without_is_resend(self, monkeypatch):
        from kairon import create_argument_parser
        import sys

        test_args = ["kairon", "broadcast", "test_bot", "test_user", "65432123456789876543"]
        monkeypatch.setattr(sys, 'argv', test_args)

        parser = create_argument_parser()
        args = parser.parse_args()

        assert hasattr(args, 'is_resend')
        assert args.is_resend == "False"

        with mock.patch('kairon.events.definitions.message_broadcast.MessageBroadcastEvent.execute',
                        autospec=True):
            cli()
