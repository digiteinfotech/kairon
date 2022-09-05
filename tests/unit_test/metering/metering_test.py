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
        test_chat_count = MeteringProcessor.get_logs(account, metric_type=MetricType.test_chat)
        prod_chat_count = MeteringProcessor.get_logs(account, metric_type=MetricType.prod_chat)
        del test_chat_count[0]["timestamp"]
        del test_chat_count[1]["timestamp"]
        assert test_chat_count[0]['bot'] in {'rhft284', 'abcb345'}
        assert test_chat_count[0]['account'] == 12345
        assert test_chat_count[0]['metric_type'] == 'test_chat'
        assert test_chat_count[1]['bot'] in {'rhft284', 'abcb345'}
        assert test_chat_count[1]['account'] == 12345
        assert test_chat_count[1]['metric_type'] == 'test_chat'
        del prod_chat_count[0]["timestamp"]
        del prod_chat_count[1]["timestamp"]
        print(prod_chat_count)
        assert prod_chat_count[0]['bot'] in {'bfg4657', 'abcb345'}
        assert prod_chat_count[0]['account'] == 12345
        assert prod_chat_count[0]['metric_type'] == 'prod_chat'
        assert prod_chat_count[1]['bot'] in {'bfg4657', 'abcb345'}
        assert prod_chat_count[1]['account'] == 12345
        assert prod_chat_count[1]['metric_type'] == 'prod_chat'
        assert prod_chat_count == [{'bot': 'bfg4657', 'account': 12345, 'metric_type': 'prod_chat'},
                                   {'bot': 'abcb345', 'account': 12345, 'metric_type': 'prod_chat'}]
