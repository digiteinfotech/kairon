import pandas as pd
from .generator import QuestionGenerator
from .web_scraper import WEB_SCRAPPER
class WebsiteQAGenerator:
    @staticmethod
    def get_qa_data(url,max_pages):
        pages = WEB_SCRAPPER.scrape_pages(url,max_pages)
        qa_data=[]
        for i in range(len(pages)):
            for j in range(len(pages[i]['text'])):
                try:
                    for k in range(len(pages[i]['text'][j])):
                        try:
                            link = """ <a target="_blank" href={}> LEARN MORE</a>""".format(pages[i]['url'])
                            context = pages[i]['text'][j][k]
                            questions = QuestionGenerator.generate(context)
                            if len(questions)!=0 and questions['status']== 'success':
                                qa_data.append({"questions":questions['questions'],"answer":context+link})
                        except:
                            pass
                except:
                    pass
        return qa_data
                