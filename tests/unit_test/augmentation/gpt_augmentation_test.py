from augmentation.gpt3_question_generator.gpt_generator import GPT3QuestionGenerator
from augmentation.gpt3_question_generator.models import AugmentationRequest
from kairon.utils import Utility
import pytest
import os
from mongoengine import connect


@pytest.fixture(autouse=True)
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_evironment()
    connect(host=Utility.environment['database']["url"])


def mock_augment_questions(*args, **kwargs):
    return True


def test_generate_questions(monkeypatch):
    monkeypatch.setattr(GPT3QuestionGenerator, 'augment_questions', mock_augment_questions)

    request_data = AugmentationRequest(api_key="MockKey",
                                       data=["Are there any more test questions?"], num_responses=2)

    gpt3_generator = GPT3QuestionGenerator(request_data=request_data)
    augmented_questions = gpt3_generator.augment_questions()

    assert augmented_questions is True
