import nlpaug.augmenter.word as naw
from nlpaug.util.text.tokenizer import split_sentence
import re


class QuestionGenerator:
    """
    Class contains logic for augmenting text
    """

    aug = naw.ContextualWordEmbsAug(model_path="bert-base-uncased", action="substitute")
    aug_single = naw.SynonymAug(aug_src="wordnet")

    @staticmethod
    def augment(text):
        """
        checks whether to apply synonym or contextual augmentation

        :param text:
        :return:
        """
        tokens = split_sentence(re.sub("[^a-zA-Z0-9 ]+", "", text))
        if len(tokens) > 1:
            return QuestionGenerator.aug.augment(text, n=10, num_thread=4)
        else:
            return QuestionGenerator.aug_single.augment(tokens[0], n=10)

    @staticmethod
    async def generateQuestions(texts):
        """
        generates a list of variations for a given sentence/question

        :param texts: list of text
        :return: list of variations
        """
        if type(texts) == str:
            texts = [texts]

        result = [QuestionGenerator.augment(text) for text in texts]

        return sum(result, [])
