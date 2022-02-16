import responses

from augmentation.knowledge_graph import training_data_generator
from augmentation.knowledge_graph.cli.training_data_generator_cli import parse_document_and_generate_training_data
from augmentation.knowledge_graph.cli.utility import TrainingDataGeneratorUtil
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
        print(actual)
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


class TestCli:

    @responses.activate
    def test_parse_document_and_generate_training_data_failure(self, monkeypatch):
        def raise_exception(*args, **kwargs):
            raise Exception("exception msg")

        responses.add(
            responses.PUT,
            "http://localhost:5000/api/bot/update/data/generator/status",
            status=200,
            json={"success":True, "data":None, "message":None, "error_code":0}
        )

        monkeypatch.setattr(TrainingDataGeneratorUtil, "fetch_latest_data_generator_status", raise_exception)
        parse_document_and_generate_training_data("http://localhost:5000", "testUser", "testtoken")

    @responses.activate
    def test_parse_document_and_generate_training_data_no_doc_path(self, monkeypatch):
        responses.add(
            responses.PUT,
            "http://localhost:5000/api/bot/update/data/generator/status",
            status=200,
            json={"success": True, "data": None, "message": None, "error_code": 0}
        )

        responses.add(
            responses.GET,
            "http://localhost:5000/api/bot/data/generation/latest",
            status=200,
            json={"success":True, "data":None, "message":None, "error_code":0}
        )
        parse_document_and_generate_training_data("http://localhost:5000", "testUser", "testtoken")

    @responses.activate
    def test_fetch_latest_data_generator_status(self, monkeypatch):
        responses.add(
            responses.GET,
            "http://localhost:5000/api/bot/data/generation/latest",
            status=200,
            json={"data": {"document_path": "test/path"}, "success": True, "message": None, "error_code": 0}
        )
        resp = TrainingDataGeneratorUtil.fetch_latest_data_generator_status("http://localhost:5000", "testUser",
                                                                            "testtoken")
        assert resp['document_path'] == 'test/path'

    @responses.activate
    def test_fetch_latest_data_generator_status_none(self, monkeypatch):
        responses.add(
            responses.GET,
            "http://localhost:5000/api/bot/data/generation/latest",
            status=200,
            json={"data": None, "success": True, "message": None, "error_code": 0}
        )
        resp = TrainingDataGeneratorUtil.fetch_latest_data_generator_status("http://localhost:5000", "testUser",
                                                                            "testtoken")
        assert resp is None

    @responses.activate
    def test_set_training_data_status(self, monkeypatch):
        responses.add(
            responses.PUT,
            "http://localhost:5000/api/bot/update/data/generator/status",
            status=200,
            json={"error_code": 0}
        )
        TrainingDataGeneratorUtil.set_training_data_status("http://localhost:5000",
                                                           {"status": "Fail", "exception": "exception msg"},
                                                           "user", "token")
