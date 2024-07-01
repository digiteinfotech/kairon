from augmentation.paraphrase.gpt3.generator import GPT3ParaphraseGenerator
from augmentation.paraphrase.gpt3.models import GPTRequest
from augmentation.paraphrase.gpt3.gpt import GPT
from openai.resources.completions import Completions
import pytest
import responses

def mock_create(*args, **kwargs):
    class MockOutput:

        class MockText:
            text = "Response text from gpt3"

        choices = [MockText(), MockText()]

    return MockOutput()


def mock_submit_request(*args, **kwargs):

    class MockOutput:

        class MockText:
            def __init__(self, text):
                self.text = text

        choices = [
            MockText("output: Are there any further test questions?"),
            MockText("output: Are there any further test questions."),
            MockText("output: Are there any more test questions?Input: My friend has an athletic scholarship to the University of Arkansas"),
            MockText("output: Is there another test question?"),
            MockText("output: Is there another test question"),
            MockText("output: Is there another Test Question?"),
            MockText("output: Are there any more test questions?"),
            MockText("output: Are there any more test questions."),
            MockText("output:Are there more test questions?"),
            MockText("output:"),
            MockText("output: "),
            MockText("output: ."),
            MockText("output:?")
        ]

    return MockOutput()


def test_questions_set_generation(monkeypatch):
    monkeypatch.setattr(GPT, 'submit_request', mock_submit_request)

    request_data = GPTRequest(api_key="MockKey",
                              data=["Are there any more test questions?"], num_responses=13)

    gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
    augmented_questions = gpt3_generator.paraphrases()

    expected_augmented_questions = {
        "Are there any further test questions?",
        "Is there another test question?",
        "Are there more test questions?"
    }
    assert augmented_questions == expected_augmented_questions


def test_generate_questions(monkeypatch):
    monkeypatch.setattr(Completions, 'create', mock_create)

    request_data = GPTRequest(api_key="MockKey",
                              data=["Are there any more test questions?"], num_responses=2)

    gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
    augmented_questions = gpt3_generator.paraphrases()

    assert augmented_questions == {"Response text from gpt3"}


def test_generate_questions_empty_api_key(monkeypatch):
    monkeypatch.setattr(Completions, 'create', mock_create)

    request_data = GPTRequest(api_key="",
                              data=["Are there any more test questions?"], num_responses=2)

    with pytest.raises(Exception):
        gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
        gpt3_generator.paraphrases()


def test_generate_questions_empty_data(monkeypatch):
    monkeypatch.setattr(Completions, 'create', mock_create)

    request_data = GPTRequest(api_key="MockKey",
                              data=[], num_responses=2)
    with pytest.raises(Exception):
        gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
        gpt3_generator.paraphrases()

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


@responses.activate
def test_generate_questions_invalid_api_key():
    from openai import APIError

    responses.add(url="https://api.openai.com/v1/engines/davinci/completions",
                  method="POST",
                  status=500,
                  body="Incorrect API key provided: InvalidKey. You can find your API key at https://beta.openai.com.")
    request_data = GPTRequest(api_key="InvalidKey",
                              data=["Are there any more test questions?"], num_responses=2)

    gpt3_generator = GPT3ParaphraseGenerator(request_data=request_data)
    with pytest.raises(APIError, match=r'.*Incorrect API key provided: InvalidKey. You can find your API key at https://platform.openai.com/account/..*'):
        gpt3_generator.paraphrases()

