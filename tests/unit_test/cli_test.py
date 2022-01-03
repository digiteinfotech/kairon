import pytest
import os

from kairon.cli.importer import validate_and_import
from kairon.cli.training import train
from kairon.cli.testing import run_tests_on_model
from kairon.cli.website_qna_generator import website_qna_generator
from kairon.events.events import EventsTrigger
from kairon.shared.utils import Utility
from mongoengine import connect
import mock
import argparse
from kairon import cli


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

        monkeypatch.setattr(EventsTrigger, "triggerargs_model_testing", mock_testing)
        cli()


class TestWebsiteQnaGeneratorCli:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(
                    func=website_qna_generator, bot="test_cli", user="testUser", url="kairon.digite.com", depth=5))
    def test_parse_website_and_generate_training_data_failure(self, monkeypatch):
        def __raise_exception(*args, **kwargs):
            raise Exception("Could not connect to website")

        monkeypatch.setattr(EventsTrigger, "trigger_qna_generator_for_website", __raise_exception)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(
                    func=website_qna_generator, bot="test_cli", user="testUser", url="kairon.digite.com", depth=5))
    def test_parse_website_and_generate_training_data(self, monkeypatch):
        def __mock_response(*args, **kwargs):
            return None

        monkeypatch.setattr(EventsTrigger, "trigger_qna_generator_for_website", __mock_response)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=website_qna_generator))
    def test_parse_website_and_generate_training_data_no_arguments(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'bot'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=website_qna_generator, bot="test_cli"))
    def test_parse_website_and_generate_training_data_no_argument_user(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'user'")

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(func=website_qna_generator, bot="test_cli", user="testUser"))
    def test_parse_website_and_generate_training_data_no_argument_website_url(self, monkeypatch):
        with pytest.raises(AttributeError) as e:
            cli()
        assert str(e).__contains__("'Namespace' object has no attribute 'url'")
