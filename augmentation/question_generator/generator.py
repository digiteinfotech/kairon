from question_generation import pipeline


class QuestionGenerator:
    nlp = pipeline('e2e-qg')

    @staticmethod
    def generate(self,text: str):
        return QuestionGenerator.nlp(text)