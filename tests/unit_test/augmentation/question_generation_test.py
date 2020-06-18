import asyncio

from augmentation.generator import QuestionGenerator


class TestQuestionGeneration:

    def test_generate_questions(self):
        expected = ["where is digite now ?", "where is it located ?", "how is digite located ?",'ally']
        loop = asyncio.new_event_loop()
        actual = loop.run_until_complete(QuestionGenerator.generateQuestions('where is digite located?'))
        actual_token = loop.run_until_complete(QuestionGenerator.generateQuestions('friend'))
        print(actual)
        print(actual_token)
        assert any(text in expected for text in  actual) and expected[3] in actual_token
