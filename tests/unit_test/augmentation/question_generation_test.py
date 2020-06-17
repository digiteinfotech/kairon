import asyncio

from augmentation.generator import QuestionGenerator


class TestQuestionGeneration:
    def test_generate_questions(self):
        expected  = "where was digite located ?"
        loop = asyncio.new_event_loop()
        actual = loop.run_until_complete(QuestionGenerator.generateQuestions('where is digite located?'))
        assert expected in actual
