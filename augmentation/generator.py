# pip install nlpaug numpy matplotlib python-dotenv
# should have torch (>=1.2.0) and transformers (>=2.5.0) installed as well
import nlpaug.augmenter.word as naw
from nlpaug.util.text.tokenizer import split_sentence
import re


class QuestionGenerator:
    aug = naw.ContextualWordEmbsAug(model_path='bert-base-uncased', action="substitute")
    aug_single = naw.SynonymAug(aug_src='wordnet')

    @staticmethod
    def augment(text):
        tokens = split_sentence(re.sub('[^a-zA-Z0-9 ]+', '', text))
        if len(tokens) > 1:
            return QuestionGenerator.aug.augment(text, n=10, num_thread=4)
        else:
            return QuestionGenerator.aug_single.augment(tokens[0], n=10)

    @staticmethod
    async def generateQuestions(texts):
        """ This function generates a list of variations for a given sentence/question.
            E.g. await QuestionGenerator.generateQuestions('your question') will return the list
            of variations for that particular question """

        if type(texts) == str:
            texts = [texts]

        result = [QuestionGenerator.augment(text) for text in texts]

        return sum(result, [])