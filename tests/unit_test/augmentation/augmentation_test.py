from augmentation.paraphrase.paraphrasing import ParaPhrasing
from augmentation.question_generator.generator import QuestionGenerator

class TestQuestionGeneration:

    def test_generate_paraphrases(self):
        expected = ['Where is digite located?',
                    'Where is digite?',
                    'What is the location of digite?',
                    'Where is the digite located?',
                    'Where is it located?',
                    'What location is digite located?',
                    'Where is the digite?',
                    'where is digite located?',
                    'Where is digite situated?',
                    'digite is located where?']
        actual = ParaPhrasing.paraphrases('where is digite located?')
        assert any(text in expected for text in actual)

    def test_generate_praraphrases_from_token(self):
        expected = ['A friend.',
                    'A friend of mine.',
                    'a friend',
                    'My friend.',
                    'I have a friend.',
                    'A friend',
                    'A friend to me.',
                    'A good friend.',
                    'Person of interest, friend.',
                    'The friend.']
        actual = ParaPhrasing.paraphrases('friend')
        assert any(text in expected for text in actual)

    def test_generate_paraphrases_from_token_special(self):
        expected = ['A friend!',
                    "I'm a friend!",
                    'I am a friend!',
                    'My friend!',
                    "It's a friend!",
                    "That's a friend!",
                    'Someone is a friend!',
                    'You are a friend!',
                    "I'm your friend!",
                    "I'm a friend."]

        actual = ParaPhrasing.paraphrases('friend! @#.')
        assert any(text in expected for text in actual)

    def test_generate_questions_from_passage(self):
        actual = QuestionGenerator.generate("Python is a programming language. Created by Guido van Rossum and first released in 1991.")
        print(actual)
        expected = ["Who created Python?", "When was Python first released?"]
        assert all(text in expected for text in actual)