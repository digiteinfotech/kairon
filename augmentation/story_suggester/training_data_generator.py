from augmentation.paraphrase.paraphrasing import ParaPhrasing
from augmentation.story_suggester.website_parser import WebsiteParser
from keybert import KeyBERT

from kairon.api.models import TrainingData


class WebsiteTrainingDataGenerator:

    """Class contains logic to retrieve intents, training examples and responses from websites"""

    def __init__(self, initial_link, depth=0):
        self.initial_link = initial_link
        self.depth = depth
        self.kw_model = KeyBERT()

    def get_training_data(self):
        data = WebsiteParser().get_qna(self.initial_link, self.depth)

        training_data = []
        for i, item in enumerate(data.items()):

            training_example = item[0]
            response = item[1]
            key_tokens = self.kw_model.extract_keywords(training_example, keyphrase_ngram_range=(1, 3), stop_words='english', top_n=1)[0][0]
            intent = key_tokens.replace(' ', '_') + "_" + str(i)
            training_examples = ParaPhrasing.paraphrases(training_example) + [training_example]

            data_obj = TrainingData()
            data_obj.intent = intent.lower().strip()
            data_obj.training_examples = training_examples
            data_obj.response = response

            training_data.append(data_obj)

        return training_data
