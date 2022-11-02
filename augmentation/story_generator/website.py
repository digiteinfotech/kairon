from augmentation.story_generator.base import TrainingDataGeneratorBase
from augmentation.utils import WebsiteParser
from keybert import KeyBERT

from kairon.exceptions import AppException


class WebsiteTrainingDataGenerator(TrainingDataGeneratorBase):

    """Class contains logic to retrieve intents, training examples and responses from websites"""

    def __init__(self, initial_link, depth=0):
        self.initial_link = initial_link
        self.depth = depth
        self.kw_model = KeyBERT()

    def extract(self):
        data, answer_citation = WebsiteParser.get_qna(self.initial_link, self.depth)
        if not data:
            raise AppException("No data could be scraped!")

        training_data = []
        for i, item in enumerate(data.items()):
            training_example = item[0]
            response = item[1]
            key_tokens = self.kw_model.extract_keywords(training_example, keyphrase_ngram_range=(1, 3), stop_words='english', top_n=1)[0][0]
            intent = key_tokens.replace(' ', '_') + "_" + str(i)
            training_examples = WebsiteTrainingDataGenerator.__generate_questions_from_scraped_data(training_example, response)
            if WebsiteParser.check_word_count(response) > 40:
                response = WebsiteParser.trunc_answer(response, answer_citation[response])
            training_data.append({
                "intent": intent,
                "training_examples": [{"training_example": t_example} for t_example in training_examples],
                "response": response
            })

        return training_data

    @staticmethod
    def __generate_questions_from_scraped_data(questions, answer):
        from augmentation.paraphrase.paraphrasing import ParaPhrasing
        from augmentation.question_generator.generator import QuestionGenerator

        if len(answer) < 50:
            questions = ParaPhrasing.paraphrases(questions) + [questions]
        else:
            questions = QuestionGenerator.generate(answer)
        return questions
