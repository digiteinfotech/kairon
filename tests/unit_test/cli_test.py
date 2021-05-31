import pytest
import os

from kairon.cli.data_importer import validate_and_import
from kairon.cli.training import train
from kairon.events.events import EventsTrigger
from kairon.utils import Utility
from mongoengine import connect
import mock
import argparse
from kairon import cli


class TestTrainingCli:

    @pytest.fixture(autouse=True, scope="session")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])

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

    @pytest.fixture(autouse=True, scope="session")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()

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
