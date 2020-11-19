from question_generation import pipeline


class QuestionGenerator:
    """Class loads pipeline for generating questions from text"""
    
    nlp = pipeline('e2e-qg')

    @staticmethod
    def generate(text: str):
        """
        generates questions for given text

        :param text: sentence or paragraph for question generation
        :return: list of questions
        """
        return QuestionGenerator.nlp(text)