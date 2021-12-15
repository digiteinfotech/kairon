from augmentation.website_qna.utils.generator import QuestionGenerator
from augmentation.website_qna.utils.web_scraper import WEB_SCRAPPER
from augmentation.website_qna.utils.WebsiteQAGenerator import WebsiteQAGenerator
from augmentation.website_qna.cli.website_qa_generator_cli import parse_website_and_generate_training_data
from augmentation.website_qna.cli.utility import WebsiteTrainingDataGeneratorUtil
import responses
import pytest

class WebQATestQuestionGeneration:
    def positive_test_generate_questions(self):
        expected = ['what is kairon?',
                    'what does kairon do?',
                    "what is kairon's focus?",
                    'what does kairon focus on?',
                    'what does kairon aim to provide?']
        text = "kAIron is a web based microservices driven suite that helps train contextual AI assistants at scale. It is designed to make the lives of those who work with AI-assistants easy by giving them a no-coding web interface to adapt, train, test and maintain such assistants."
        actual = QuestionGenerator.generate(text)
        if actual['status'] != 'success':
            assert actual['status'] != 'success', actual['status']
        else:
            assert any(text.lower() in expected for text in actual['questions'])

    def input_too_small(self):
        error_msg = 'input too small'
        text = "Delhi is a small state."
        actual = QuestionGenerator.generate(text)
        assert actual['status'] == error_msg, "Expected error msg -> 'input too small'"

    def input_not_str(self):
        text_list = ["kAIron is a web based microservices driven suite that helps train contextual AI assistants at scale. It is designed to make the lives of those who work with AI-assistants easy by giving them a no-coding web interface to adapt, train, test and maintain such assistants."]
        actual = QuestionGenerator.generate(text_list)
        assert actual['status'] != 'success', "This test should have failed as input is list"

class WebQATestWebScrapper:
    def positive_test_web_scrapper(self):
        expected = ["kAIron is a web based microservices driven suite that helps train contextual AI assistants at scale. It is designed to make the lives of those who work with AI-assistants easy by giving them a no-coding web interface to adapt, train, test and maintain such assistants.",
        "kAIron is currently built on the RASA framework. While RASA focuses on the technology of chatbots itself, kAIron, on the other hand, focuses on technology that deals with the pre-processing of data that are needed by this framework. These include question augmentation and generation of knowledge graphs that can be used to automatically generate intents, questions and responses.",
        "kAIrons released under the Apache 2.0 license. You can find the source here https://github.com/digiteinfotech/kairon. Our teams current focus within NLP is Knowledge Graphs Dolet us knowif you are interested."]
        url = "https://www.digite.com/kairon/"
        max_pages = 2
        pages = WEB_SCRAPPER.scrape_pages(url,max_pages)
        actual = []
        for i in range(len(pages)):
            for j in pages[i]['text']:
                for k in j:
                    actual.append(k)
        assert any(text.lower() in expected for text in actual)

    def invalid_url_test_web_scrapper(self):
        url = "asdasdh.com"
        max_pages = 2
        pages = WEB_SCRAPPER.scrape_pages(url,max_pages)
        assert len(pages) == 0
    
    def pages_less_than_equal_to_0_test_web_scrapper(self):
        url = "https://www.digite.com/kairon/"
        max_pages = -1
        pages = WEB_SCRAPPER.scrape_pages(url,max_pages)
        assert len(pages) == 0

class WebQATestWebsiteQAGenerator():
    def positive_test_website_qa_generator(self):
        expected = ['what is kairon?',
                    'what does kairon do?',
                    "what is kairon's focus?",
                    'what does kairon focus on?',
                    'what does kairon aim to provide?'
                    'what is kairon built on?'
                    'what does kairon focus on?']
        url = "https://www.digite.com/kairon/"
        max_pages = 2  
        actual = []
        response = WebsiteQAGenerator.get_qa_data(url,max_pages)
        for i in response:
            actual.extend(i['question'])
        assert any(text.lower() in expected for text in actual)

    def invalid_url_test_web_scrapper(self):
        url = "asdasdh.com"
        max_pages = 2
        response = WebsiteQAGenerator.get_qa_data(url,max_pages)
        assert len(response) == 0 
    
    def pages_less_than_equal_to_0_test_web_scrapper(self):
        url = "https://www.digite.com/kairon/"
        max_pages = 0
        response = WebsiteQAGenerator.get_qa_data(url,max_pages)
        assert len(response) == 0 

    
class WebQATestCli:

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

        monkeypatch.setattr(WebsiteTrainingDataGeneratorUtil, "fetch_latest_data_generator_status", raise_exception)
        parse_website_and_generate_training_data("http://localhost:5000", "testUser", "testtoken")

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
        WebsiteTrainingDataGeneratorUtil("http://localhost:5000", "testUser", "testtoken")

    @responses.activate
    def test_fetch_latest_data_generator_status(self, monkeypatch):
        responses.add(
            responses.GET,
            "http://localhost:5000/api/bot/data/generation/latest",
            status=200,
            json={"data": {"website_url": "https://www.digite.com/kairon/","max_pages":2}, "success": True, "message": None, "error_code": 0}
        )
        resp = WebsiteTrainingDataGeneratorUtil.fetch_latest_data_generator_status("http://localhost:5000", "testUser",
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
        resp = WebsiteTrainingDataGeneratorUtil.fetch_latest_data_generator_status("http://localhost:5000", "testUser",
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
        WebsiteTrainingDataGeneratorUtil.set_training_data_status("http://localhost:5000",
                                                           {"status": "Fail", "exception": "exception msg"},
                                                           "user", "token")



