from loguru import logger
from .generator import QuestionGenerator
from .web_scraper import WebScraper
class WebsiteQnAGenerator:

    """This class is used to generate QnA for a website."""

    @staticmethod
    def get_qa_data(url: str,max_pages: int):
        """Scrape website and generate questions

        :param url: url of website
        :param max_pages: maximum number of pages to extract
        :return: List of dictionaries contaning questions and answer
        """
        pages = WebScraper.scrape_pages(url,max_pages)
        qa_data=[]
        for i in range(len(pages)):
            for j in range(len(pages[i]['text'])):
                try:
                    for k in range(len(pages[i]['text'][j])):
                        link = """ <a target="_blank" href={}> LEARN MORE</a>""".format(pages[i]['url'])
                        context = pages[i]['text'][j][k]
                        questions = QuestionGenerator.generate(context)
                        if len(questions)!=0 and questions['status']== 'success':
                            qa_data.append({"questions":questions['questions'],"answer":context+link})
                except Exception as ex:
                    logger.exception("Exception occured in WebsiteQnAGenerator: {}".format(ex))
        return qa_data
                