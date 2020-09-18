import asyncio

from augmentation.paraphrase.generator import QuestionGenerator


class TestQuestionGeneration:

    def test_generate_questions(self):
        expected = ["where is digite now ?", "where is it located ?", "how is digite located ?"]
        loop = asyncio.new_event_loop()
        actual = loop.run_until_complete(QuestionGenerator.generateQuestions('where is digite located?'))
        assert any(text in expected for text in actual)

    def test_generate_questions_token(self):
        expected = ['ally', 'admirer']
        loop = asyncio.new_event_loop()
        actual = loop.run_until_complete(QuestionGenerator.generateQuestions('friend'))
        assert any(text in expected for text in actual)

    def test_generate_questions_token_special(self):
        expected = ['ally', 'admirer']
        loop = asyncio.new_event_loop()
        actual = loop.run_until_complete(QuestionGenerator.generateQuestions('friend! @#.'))
        assert any(text in expected for text in actual)
