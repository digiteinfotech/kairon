import openai
from .gpt import GPT, Example
from .models import AugmentationRequest
from .gpt_processor.gpt_processors import GPT3ApiKey


class GPT3QuestionGenerator:

    def __init__(self, request_data: AugmentationRequest, user: str):

        self.gpt_user = GPT3ApiKey.get_user(user)
        openai.api_key = self.gpt_user["api_key"]

        self.text = request_data.text
        self.num_responses = request_data.num_responses

        self.gpt = GPT(engine=request_data.engine,
                       temperature=request_data.temperature,
                       max_tokens=request_data.max_tokens)

        self.gpt.add_example(Example('Will I need to irrigate my groundnut field tomorrow?',
                                     'Will my groundnut field need to be watered tomorrow?'))
        self.gpt.add_example(Example('How can I get the vaccine for covid 19?',
                                     'How can I get vaccinated for covid 19?'))

    def augment_questions(self):
        output = self.gpt.submit_request(self.text, self.num_responses)

        questions_set = set()

        for i in range(self.num_responses):
            questions_set.add(output.choices[i].text.replace('output: ', '').replace('\n', ''))

        return questions_set
