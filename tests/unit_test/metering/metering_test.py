import os

import pytest
from mongoengine import connect

from kairon import Utility
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor
from kairon.shared.metering.data_object import Metering


class TestMetering:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_email_configuration()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        yield None

    def test_add_metrics_test_chat(self):
        bot = 'abcb345'
        bot1 = 'rhft284'
        account = 12345
        metric_type = MetricType.test_chat
        assert MeteringProcessor.add_metrics(bot, account, metric_type)
        assert MeteringProcessor.add_metrics(bot1, account, MetricType.test_chat)

    def test_add_metrics_prod_chat(self):
        bot = 'abcb345'
        bot1 = 'bfg4657'
        account = 12345
        assert MeteringProcessor.add_metrics(bot, account, MetricType.prod_chat)
        assert MeteringProcessor.add_metrics(bot1, account, MetricType.prod_chat)

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

    def test_update_metrics_conversation_feedback(self):
        bot = 'test_update_metrics_conversation_feedback'
        account = 12345
        data = {"feedback": "",
                "rating": 1,
                "botId": "6322ebbb3c62158dab4aee71",
                "botReply": [{"text":"Hello! How are you?"}],
                "userReply": "",
                "date":"2023-07-17T06:48:02.453Z",
                "sender_id": None
                }
        metric_type = MetricType.conversation_feedback
        id = MeteringProcessor.add_metrics(bot, account, metric_type, **data)
        value = Metering.objects().get(id=id)
        assert value.feedback == ""
        MeteringProcessor.update_metrics(id, bot, metric_type, **{"feedback": "test"})
        value = Metering.objects().get(id=id)
        assert value.feedback == "test"

    def test_update_metrics_conversation_feedback_add_field(self):
        bot = 'test_update_metrics_conversation_feedback'
        account = 12345
        data = {"rating": 1,
                "botId": "6322ebbb3c62158dab4aee71",
                "botReply": [{"text":"Hello! How are you?"}],
                "userReply": "",
                "date":"2023-07-17T06:48:02.453Z",
                "sender_id": None
                }
        metric_type = MetricType.conversation_feedback
        id = MeteringProcessor.add_metrics(bot, account, metric_type, **data)
        value = Metering.objects().get(id=id)
        assert not hasattr(value, "feedback")
        MeteringProcessor.update_metrics(id, bot, metric_type, **{"feedback": "test"})
        value = Metering.objects().get(id=id)
        assert value.feedback == "test"

    def test_update_invalid_metrics_conversation_feedback(self):
        bot = 'test_update_metrics_conversation_feedback'
        with pytest.raises(ValueError, match="Invalid metric type"):
            MeteringProcessor.update_metrics("test", bot, "test", **{"feedback": "test"})

