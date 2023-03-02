import pytest
import os
from kairon.shared.utils import Utility
from mongoengine import connect
import mock
from kairon.shared.llm.gpt3 import GPT3FAQEmbedding, LLMBase
from kairon.shared.llm.factory import LLMFactory


class TestLLM:
    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_llm_base_train(self):
        with pytest.raises(Exception):
            base = LLMBase()
            base.train()

    def test_llm_base_predict(self):
        with pytest.raises(Exception):
            base = LLMBase()
            base.predict("Sample")

    def test_llm_base_predict(self):
        with pytest.raises(Exception):
            base = LLMBase()
            base.predict("Sample")