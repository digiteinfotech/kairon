import pytest
import responses

from augmentation.knowledge_graph import training_data_generator
from augmentation.paraphrase.paraphrasing import ParaPhrasing
from augmentation.question_generator.generator import QuestionGenerator
from augmentation.knowledge_graph.document_parser import DocumentParser

pdf_file = "./tests/testing_data/file_data/sample1.pdf"
docx_file = "./tests/testing_data/file_data/sample1.docx"


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
        actual = QuestionGenerator.generate(
            "Python is a programming language. Created by Guido van Rossum and first released in 1991.")
        expected = ["What is the name of the programming language that Python was created by?","Who created Python?", "When was Python first released?"]
        assert all(text in expected for text in actual)


class TestDocumentParser:

    def test_doc_structure_pdf(self):
        structure, list_sentences = DocumentParser.parse(pdf_file)
        assert structure[31] == [32]
        assert list_sentences[0] == '<h1> 1 Introducing  ONEPOINT Projects'
        final_list = training_data_generator.TrainingDataGenerator.generate_intent(structure, list_sentences)
        expected = 'root_1-Introducing--ONEPOINT-Projects_1.3-Basic-Concepts_1.3.8-Open-Design'
        assert any(item['intent'] == expected for item in final_list)

    def test_doc_structure_docx(self):
        structure, list_sentences = DocumentParser.parse(docx_file)
        assert structure[23] == [24, 25]
        assert list_sentences[0] == '<h0> Demonstration of DOCX support in calibre'
        final_list = training_data_generator.TrainingDataGenerator.generate_intent(structure, list_sentences)
        expected = 'root_Demonstration-of-DOCX-support-in-calibre'
        assert any(item['intent'] == expected for item in final_list)


