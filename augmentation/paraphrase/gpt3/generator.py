from .gpt import GPT, Example
from .models import GPTRequest
import string


class GPT3ParaphraseGenerator:

    """Class creates GPT model for text augmentation"""
    def __init__(self, request_data: GPTRequest):

        self.api_key = request_data.api_key

        self.data = request_data.data
        self.num_responses = request_data.num_responses

        self.gpt = GPT(engine=request_data.engine,
                       temperature=request_data.temperature,
                       max_tokens=request_data.max_tokens)

        self.gpt.add_example(Example('Will I need to irrigate my groundnut field tomorrow?',
                                     'Will my groundnut field need to be watered tomorrow?'))
        self.gpt.add_example(Example('How can I get the vaccine for covid 19?',
                                     'How can I get vaccinated for covid 19?'))

    def paraphrases(self):
        """This function creates prompt using user's input and sends a
        request to gpt3's Completion api for question augmentation

        :param self:
        :return: list of questions"""

        if not self.api_key:
            raise Exception("API key cannot be empty.")

        if self.data:
            data_present = all([example for example in self.data])
            if not data_present:
                raise Exception("Questions data cannot be empty.")
        else:
            raise Exception("Questions data cannot be empty.")

        # run loop for each question in data var
        questions_set = set()

        # adding prompts sent by user to this list so that we can reject duplicate sentences from gpt response
        mod_data = [sentence.translate(str.maketrans('', '', string.punctuation)).lower().strip() for sentence in self.data]
        questions_wo_punctuation = set(mod_data)

        for text in self.data:
            output = self.gpt.submit_request(text, self.num_responses, self.api_key)

            for i in range(self.num_responses):

                aug_question = output.choices[i].text.replace('output:', '').replace('\n', '').strip()
                if len(aug_question) < 2*len(text):
                    raw_question = aug_question.translate(str.maketrans('', '', string.punctuation)).lower()

                    if raw_question not in questions_wo_punctuation and raw_question != "":
                        questions_wo_punctuation.add(raw_question)
                        questions_set.add(aug_question)

        return questions_set
