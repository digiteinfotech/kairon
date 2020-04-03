import pytest
from bot_trainer.QuestionGeneration import QuestionGeneration
import asyncio

class TestQuestionGeneration:

    def test_generate_questions(self):
        result = ['where is digite stationed ?', 'where is digite constructed ?', 'where is digite resided ?', 'where is digite headquartered ?', 'where is digite situated ?', 'where is digite operated ?', 'where is digite resides ?', 'where is digite housed ?', 'where is digite sited ?', 'where is digite positioned ?']
        loop = asyncio.new_event_loop()
        response = loop.run_until_complete(QuestionGeneration.generateQuestions('where is digite located?'))
        assert response == result