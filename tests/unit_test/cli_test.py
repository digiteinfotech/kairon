import pytest
import os
from kairon.utils import Utility
from mongoengine import connect
import mock
import argparse
from kairon import cli


class TestCli:

    @pytest.fixture(autouse=True, scope="session")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(kwarg1="--train"))
    def test_kairon_cli_train_no_arguments(self, monkeypatch):

        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        with pytest.raises(AttributeError) as e:
            cli()
            assert e == "'Namespace' object has no attribute 'bot'"

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(kwarg1="--train", kwarg2="tests"))
    def test_kairon_cli_train_no_argument_user(self, monkeypatch):
        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        with pytest.raises(AttributeError) as e:
            cli()
            assert e == "'Namespace' object has no attribute 'user'"

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(train="--train", bot="tests", user="testUser"))
    def test_kairon_cli_train(self, monkeypatch):
        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        cli()

    @mock.patch('argparse.ArgumentParser.parse_args',
                return_value=argparse.Namespace(train="--train", bot="tests", user="testUser", token="test"))
    def test_kairon_cli_train_with_all_arguments(self, monkeypatch):
        def mock_training(*args, **kwargs):
            return "model"

        monkeypatch.setattr(Utility, "start_training", mock_training)
        cli()