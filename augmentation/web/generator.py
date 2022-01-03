from loguru import logger

from augmentation.exception import AugmentationException
from augmentation.question_generator.generator import QuestionGenerator
from augmentation.web.scraper import WebScraper


class WebsiteQnAGenerator:

    """Generates QnA from a website content."""

    @staticmethod
    def get_qa_data(url: str, max_pages: int):
        """
        Scrape website and generate questions.

        :param url: url of website
        :param max_pages: maximum number of pages to extract
        :return: List of dictionaries contaning questions and answer
        """
        pages = WebScraper.scrape_pages(url, max_pages)
        qna = []
        for i, _ in enumerate(pages):
            for j, _ in enumerate(pages[i]['text']):
                try:
                    for k, _ in enumerate(pages[i]['text'][j]):
                        link = """ <a target="_blank" href={}> LEARN MORE</a>""".format(pages[i]['url'])
                        context = pages[i]['text'][j][k]
                        questions = QuestionGenerator.generate(context)
                        if questions:
                            qna.append({"training_examples": questions, "response": context + link})
                except AugmentationException as ex:
                    logger.exception(ex)
        return qna
