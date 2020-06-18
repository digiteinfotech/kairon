# pip install nlpaug numpy matplotlib python-dotenv
# should have torch (>=1.2.0) and transformers (>=2.5.0) installed as well
import nlpaug.augmenter.word as naw
from nltk.tokenize import word_tokenize
import re


class QuestionGenerator:
    aug = naw.ContextualWordEmbsAug(model_path='bert-base-uncased', action="substitute", stopwords=['digite'])
    aug_single = naw.SynonymAug(aug_src='wordnet')

    @staticmethod
    async def generateQuestions(texts):
        """ This function generates a list of variations for a given sentence/question.
            E.g. await QuestionGenerator.generateQuestions('your question') will return the list
            of variations for that particular question """

        if type(texts) == str:
            texts = [texts]

        result = [QuestionGenerator.aug.augment(text, n=10, num_thread=4)
                  if len(word_tokenize(re.sub('[^a-zA-Z0-9 ]+', '', text))) > 1
                  else QuestionGenerator.aug_single.augment(text, n=10)
                  for text in texts]

        return sum(result, [])