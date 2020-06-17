# pip install nlpaug numpy matplotlib python-dotenv
# should have torch (>=1.2.0) and transformers (>=2.5.0) installed as well
import nlpaug.augmenter.word as naw


class QuestionGenerator:
    aug = naw.ContextualWordEmbsAug(model_path='bert-base-uncased', action="substitute")

    @staticmethod
    async def generateQuestions(texts):
        """ This function generates a list of variations for a given sentence/question.
            E.g. await QuestionGenerator.generateQuestions('your question') will return the list
            of variations for that particular question """
        result = []
        if type(texts) == str:
            texts = [texts]

        for text in texts:
            augmented_text = QuestionGenerator.aug.augment(text, n=10, num_thread=4)
            result += augmented_text

        return result