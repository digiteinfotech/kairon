from augmentation.paraphrase.gpt3.generator import GPT3ParaphraseGenerator
from augmentation.paraphrase.gpt3.models import GPTRequest
import openai
from kairon.exceptions import AppException
import pytest
from augmentation.paraphrase.server import gpt_paraphrases


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


def test_generate_questions_empty_api_key(monkeypatch):
    monkeypatch.setattr(openai.Completion, 'create', mock_create)

    request_data = GPTRequest(api_key="",
                              data=["Are there any more test questions?"], num_responses=2)

    with pytest.raises(Exception):
        gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
        gpt3_generator.paraphrases()


def test_generate_questions_empty_data(monkeypatch):
    monkeypatch.setattr(openai.Completion, 'create', mock_create)

    request_data = GPTRequest(api_key="MockKey",
                              data=[""], num_responses=2)
    with pytest.raises(Exception):
        gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
        gpt3_generator.paraphrases()

    request_data = GPTRequest(api_key="MockKey",
                              data=["Are there any more test questions?", "Are there more questions?", ""],
                              num_responses=2)
    with pytest.raises(Exception):
        gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
        gpt3_generator.paraphrases()

    request_data = GPTRequest(api_key="MockKey",
                              data=["Are there any more test questions?", "Are there more questions?"],
                              num_responses=2)
    gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
    resp = gpt3_generator.paraphrases()
    assert resp == {'Response text from gpt3'}


def test_generate_questions_invalid_api_key():
    request_data = GPTRequest(api_key="InvalidKey",
                              data=["Are there any more test questions?"], num_responses=2)

    gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
    try:
        gpt3_generator.paraphrases()
    except Exception as e:
        assert str(e) == "Incorrect API key provided: InvalidKey. You can find your API key at https://beta.openai.com."

    with pytest.raises(Exception):
        gpt3_generator.paraphrases()
