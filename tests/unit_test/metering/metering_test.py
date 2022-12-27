import os

import pytest
import responses
from mongoengine import connect

from kairon import Utility
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor


class TestMetering:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_email_configuration()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        yield None

    @responses.activate
    def test_add_metrics_test_chat(self):
        bot = 'abcb345'
        bot1 = 'rhft284'
        account = 12345
        metric_type = MetricType.test_chat
        MeteringProcessor.add_metrics(bot, account, metric_type)
        MeteringProcessor.add_metrics(bot1, account, MetricType.test_chat)

    def test_add_metrics_prod_chat(self):
        bot = 'abcb345'
        bot1 = 'bfg4657'
        account = 12345
        MeteringProcessor.add_metrics(bot, account, MetricType.prod_chat)
        MeteringProcessor.add_metrics(bot1, account, MetricType.prod_chat)

    def test_get_metric(self):
        account = 12345
        bot = 'abcb345'
        bot1 = 'bfg4657'
        bot2 = 'rhft284'
        test_chat_count = MeteringProcessor.get_logs(account, metric_type=MetricType.test_chat, bot=bot)["logs"]
        del test_chat_count[0]["timestamp"]
        assert test_chat_count[0]['bot'] == bot
        assert test_chat_count[0]['account'] == account
        assert test_chat_count[0]['metric_type'] == MetricType.test_chat.value
        assert MeteringProcessor.get_logs(account, metric_type=MetricType.test_chat, bot=bot1)["logs"] == []
        test_chat_count = MeteringProcessor.get_logs(account, metric_type=MetricType.test_chat, bot=bot2)["logs"]
        del test_chat_count[0]["timestamp"]
        assert test_chat_count[0]['bot'] == bot2
        assert test_chat_count[0]['account'] == account
        assert test_chat_count[0]['metric_type'] == MetricType.test_chat.value
        prod_chat_count = MeteringProcessor.get_logs(account, metric_type=MetricType.prod_chat, bot=bot)["logs"]
        del prod_chat_count[0]["timestamp"]
        assert prod_chat_count[0]['bot'] == bot
        assert prod_chat_count[0]['account'] == account
        assert prod_chat_count[0]['metric_type'] == MetricType.prod_chat
        prod_chat_count = MeteringProcessor.get_logs(account, metric_type=MetricType.prod_chat, bot=bot1)["logs"]
        del prod_chat_count[0]["timestamp"]
        assert prod_chat_count[0]['bot'] == bot1
        assert prod_chat_count[0]['account'] == account
        assert prod_chat_count[0]['metric_type'] == MetricType.prod_chat
