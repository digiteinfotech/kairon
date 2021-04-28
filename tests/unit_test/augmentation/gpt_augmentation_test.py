from augmentation.paraphrase.gpt3.generator import GPT3ParaphraseGenerator
from augmentation.paraphrase.gpt3.models import GPTRequest
from kairon.utils import Utility
import pytest
import os
from mongoengine import connect
import openai


@pytest.fixture(autouse=True)
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_evironment()
    connect(host=Utility.environment['database']["url"])


def mock_create(*args, **kwargs):
    class MockOutput:

        class MockText:
            text = "Response text from gpt3"

        choices = [MockText(), MockText()]

    return MockOutput()


def test_generate_questions(monkeypatch):
    monkeypatch.setattr(openai.Completion, 'create', mock_create)

    request_data = GPTRequest(api_key="MockKey",
                                       data=["Are there any more test questions?"], num_responses=2)

    gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
    augmented_questions = gpt3_generator.paraphrases()

    assert augmented_questions == {"Response text from gpt3"}
