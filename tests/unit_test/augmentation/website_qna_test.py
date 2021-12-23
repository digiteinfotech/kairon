from augmentation.website_qna.utils.generator import QuestionGenerator
from augmentation.website_qna.utils.web_scraper import WebScraper
from augmentation.website_qna.utils.WebsiteQnAGenerator import WebsiteQnAGenerator
from augmentation.website_qna.cli.website_qna_generator_cli import parse_website_and_generate_training_data
from augmentation.website_qna.cli.utility import WebsiteTrainingDataGeneratorUtil
from bs4 import BeautifulSoup
import responses

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
        pages = WebScraper.scrape_pages(url,max_pages)
        actual = []
        for i in range(len(pages)):
            for j in pages[i]['text']:
                for k in j:
                    actual.append(k)
        assert any(text.lower() in expected for text in actual)

    def invalid_url_test_web_scrapper(self):
        url = "asdasdh.com"
        max_pages = 2
        pages = WebScraper.scrape_pages(url,max_pages)
        assert len(pages) == 0
    
    def pages_less_than_equal_to_0_test_web_scrapper(self):
        url = "https://www.digite.com/kairon/"
        max_pages = -1
        pages = WebScraper.scrape_pages(url,max_pages)
        assert len(pages) == 0

    def one_parent_and_two_bulletins_test_join_bulletins(self):
        test_input = ['parent','-bulletin1','-bulletin2']
        expected = ['parent -bulletin1 -bulletin2']
        actual = WebScraper.join_bulletins(test_input)
        assert actual[0] == expected[0]
    
    def no_bulletins_test_join_bulletins(self):
        test_input = ['text1','text2']
        expected = ['text1','text2']
        actual = WebScraper.join_bulletins(test_input)
        assert actual == expected
    
    def parent_bulletin_textt_join_bulletins(self):
        test_input = ['parent','-bulletin1','text']
        expected = ['parent -bulletin1','text']
        actual = WebScraper.join_bulletins(test_input)
        assert actual == expected
    
    def test_remove_headers_and_seprate_headers_joined_with_regular_text(self):
        with open("tests/testing_data/augmentation/test_remove_headers_and_seprate_headers_joined_with_regular_text.txt", "r",encoding='latin-1') as file:
            HTML = file.read()
        soup = BeautifulSoup(HTML, 'html.parser')
        input_list = ['Free and open stock market and financial education', 'Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.', 'Modules', '1. Introduction to Stock Markets15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.', '2. Technical Analysis22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.', '3. Fundamental Analysis16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.', '4. Futures Trading13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc', '5. Options Theory for Professional Trading25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.', '6. Option Strategies14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.', '7. Markets and Taxation7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.', '8. Currency, Commodity, and Government Securities19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.', '9. Risk Management & Trading Psychology16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading', '10. Trading Systems16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.', '11. Personal Finance (Part 1)30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.', '12. Innerworth Mind over markets603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.', '13. Integrated Financial Modelling9 chapters', 'Finance made easy for kids', 'A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.', 'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.', 'Chapter updates - 5. Options Theory for Professional Trading on November 29, 2021', 'Ch 25 Options M2M and P&L calculation', '25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021', 'Ch 9 Debt Schedule', '9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021', 'Ch 30 Basics of Macro Economics', '30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020', 'Ch 26 The Mutual Fund Portfolio', '26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020', 'Ch 25 How to analyze a debt mutual fund?', '25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..', 'Recent comments', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', 'Good luck, Yashwanth. ...17 Dec 2021', "Don't have a Zerodha account?", 'Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account']
        expected = [['Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.'], ['1. Introduction to Stock Markets 15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.'], ['2. Technical Analysis 22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.'], ['3. Fundamental Analysis 16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.'], ['4. Futures Trading 13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc'], ['5. Options Theory for Professional Trading 25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.'], ['6. Option Strategies 14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.'], ['7. Markets and Taxation 7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.'], ['8. Currency, Commodity, and Government Securities 19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.'], ['9. Risk Management & Trading Psychology 16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading'], ['10. Trading Systems 16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.'], ['11. Personal Finance (Part 1) 30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.'], ['12. Innerworth Mind over markets 603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.'], ['13. Integrated Financial Modelling 9 chapters'], ['A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.', 'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.'], ['Chapter updates  - 5. Options Theory for Professional Trading on November 29, 2021'], ['25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021'], ['9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021'], ['30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020'], ['26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020'], ['25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..'], ['...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', 'Good luck, Yashwanth. ...17 Dec 2021'], ['Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account']]
        actual = WebScraper.remove_headers_and_seprate_headers_joined_with_regular_text(input_list,soup)
        assert expected == actual

    def test_fix_incomplete_text_and_add_left_out_p_tags(self):
        with open("tests/testing_data/augmentation/test_remove_headers_and_seprate_headers_joined_with_regular_text.txt", "r",encoding='latin-1') as file:
            HTML = file.read()
        soup = BeautifulSoup(HTML, 'html.parser')
        input_list =[['Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.'], ['1. Introduction to Stock Markets 15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.'], ['2. Technical Analysis 22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.'], ['3. Fundamental Analysis 16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.'], ['4. Futures Trading 13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc'], ['5. Options Theory for Professional Trading 25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.'], ['6. Option Strategies 14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.'], ['7. Markets and Taxation 7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.'], ['8. Currency, Commodity, and Government Securities 19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.'], ['9. Risk Management & Trading Psychology 16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading'], ['10. Trading Systems 16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.'], ['11. Personal Finance (Part 1) 30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.'], ['12. Innerworth Mind over markets 603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.'], ['13. Integrated Financial Modelling 9 chapters'], ['A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.', 'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.'], ['Chapter updates  - 5. Options Theory for Professional Trading on November 29, 2021'], ['25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021'], ['9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021'], ['30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020'], ['26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020'], ['25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..'], ['...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', 'Good luck, Yashwanth. ...17 Dec 2021'], ['Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account']]
        expected = [['Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.'], ['1. Introduction to Stock Markets 15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.'], ['2. Technical Analysis 22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.'], ['3. Fundamental Analysis 16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.'], ['4. Futures Trading 13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc'], ['5. Options Theory for Professional Trading 25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.'], ['6. Option Strategies 14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.'], ['7. Markets and Taxation 7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.'], ['8. Currency, Commodity, and Government Securities 19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.'], ['9. Risk Management & Trading Psychology 16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading'], ['10. Trading Systems 16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.'], ['11. Personal Finance (Part 1) 30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.'], ['12. Innerworth Mind over markets 603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.'], ['13. Integrated Financial Modelling 9 chapters'], ['A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.', 'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.'], ['Chapter updates - 5. Options Theory for Professional Trading on November 29, 2021'], ['25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021'], ['9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021'], ['30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020'], ['26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020'], ['25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..'], ['...17 Dec 2021 ...17 Dec 2021 ...17 Dec 2021 ...17 Dec 2021 Good luck, Yashwanth. ...17 Dec 2021'], ['Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account'], ['Varsity by Zerodha 2015 2021. All rights reserved. Reproduction of the Varsity materials, text and images, is not permitted. For media queries, contact [emailprotected]']]
        actual = WebScraper.remove_headers_and_seprate_headers_joined_with_regular_text(input_list,soup)
        assert expected == actual

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
        response = WebsiteQnAGenerator.get_qa_data(url,max_pages)
        for i in response:
            actual.extend(i['question'])
        assert any(text.lower() in expected for text in actual)

    def invalid_url_test_web_scrapper(self):
        url = "asdasdh.com"
        max_pages = 2
        response = WebsiteQnAGenerator.get_qa_data(url,max_pages)
        assert len(response) == 0 
    
    def pages_less_than_equal_to_0_test_web_scrapper(self):
        url = "https://www.digite.com/kairon/"
        max_pages = 0
        response = WebsiteQnAGenerator.get_qa_data(url,max_pages)
        assert len(response) == 0 

    
class WebQATestCli:

    @responses.activate
    def test_parse_website_and_generate_training_data_failure(self, monkeypatch):
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
    def test_parse_website_and_generate_training_data_no_url(self, monkeypatch):
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
            json={"data": {"website_url": "https://www.digite.com/kairon/","max_pages":1}, "success": True, "message": None, "error_code": 0}
        )
        resp = WebsiteTrainingDataGeneratorUtil.fetch_latest_data_generator_status("http://localhost:5000", "testUser",
                                                                            "testtoken")
        assert resp['website_url'] == 'https://www.digite.com/kairon/'

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



