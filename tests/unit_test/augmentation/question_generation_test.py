import asyncio

#from augmentation.generator import QuestionGenerator


class TestQuestionGeneration:
    def test_generate_questions(self):
        expected = ['where is digite centrally located?',
                     'where is digite conveniently located?',
                     'where is digite islocated?',
                     'where is digite situated?',
                     'where is digite strategically located?']
        loop = asyncio.new_event_loop()
#        actual = loop.run_until_complete(QuestionGenerator.generateQuestions('where is digite located?'))
#        print(actual)
#        assert all([a in expected for a in actual])
