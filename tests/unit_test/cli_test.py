import pytest
import os

from kairon import cli
from kairon.cli.conversations_deletion import initiate_history_deletion_archival
from kairon.cli.importer import validate_and_import
from kairon.cli.training import train
from kairon.cli.testing import run_tests_on_model
from kairon.events.events import EventsTrigger
from kairon.shared.utils import Utility
from mongoengine import connect
import mock
import argparse


class TestTrainingCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

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
                                                import_data=False, overwrite=False))
    def test_data_importer_with_defaults(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_data_importer", mock_data_importer)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli", user="testUser",
                                                import_data=True, overwrite=True))
    def test_data_importer_all_arguments(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_data_importer", mock_data_importer)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli", user="testUser",
                                                import_data=True, overwrite=False))
    def test_data_importer_with_all_args_overwrite_false(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_data_importer", mock_data_importer)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=validate_and_import, bot="test_cli", user="testUser",
                                                import_data="yes", overwrite=False))
    def test_data_importer_import_as_string_argument(self, monkeypatch):
        def mock_data_importer(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_data_importer", mock_data_importer)
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

        monkeypatch.setattr(EventsTrigger, "trigger_model_testing", mock_testing)
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=run_tests_on_model, bot="test_cli"))
    def test_kairon_cli_test_no_argument_user(self, monkeypatch):
        def mock_testing(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_model_testing", mock_testing)
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=run_tests_on_model, bot="test_cli", user="testUser"))
    def test_kairon_cli_test(self, monkeypatch):
        def mock_testing(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_model_testing", mock_testing)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=run_tests_on_model, bot="test_cli", user="testUser", token="test"))
    def test_kairon_cli_test_with_all_arguments(self, monkeypatch):
        def mock_testing(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_model_testing", mock_testing)
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
                                                sender_id=None, month=3))
    def test_cli_history_deletion_with_defaults(self, monkeypatch):
        def mock_history_delete(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_history_deletion", mock_history_delete)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=initiate_history_deletion_archival, bot="test_cli", user="testUser",
                                                sender_id='testSender', month=1))
    def test_cli_history_deletion_all_arguments(self, monkeypatch):
        def mock_history_delete(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_history_deletion", mock_history_delete)
        cli()
