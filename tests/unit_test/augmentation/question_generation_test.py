import asyncio

from augmentation.generator import QuestionGenerator


class TestQuestionGeneration:
    def test_generate_questions(self):
        expected = [
            "where is digite located ?",
            "where is digite set ?",
            "where is digite situated ?",
            "where is digite placed ?",
        ]
        loop = asyncio.new_event_loop()
        actual = loop.run_until_complete(QuestionGenerator.generateQuestions('where is digite located?'))
        assert all([a in expected for a in actual])
