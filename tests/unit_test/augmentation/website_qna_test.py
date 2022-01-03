import pytest
import responses

from augmentation.exception import AugmentationException
from augmentation.question_generator.generator import QuestionGenerator
from augmentation.web.scraper import WebScraper
from augmentation.web.generator import WebsiteQnAGenerator
from bs4 import BeautifulSoup


class TestQuestionGeneration:

    def test_positive_test_generate_questions(self):
        expected = ['what is kairon?',
                    'what does kairon do?',
                    "what is kairon's focus?",
                    'what does kairon focus on?',
                    'what does kairon aim to provide?']
        text = "kAIron is a web based microservices driven suite that helps train contextual AI assistants at scale. It is designed to make the lives of those who work with AI-assistants easy by giving them a no-coding web interface to adapt, train, test and maintain such assistants."
        actual = QuestionGenerator.generate(text)
        print(actual)
        assert any(text.lower() in expected for text in actual)

    def test_input_too_small(self):
        text = "Delhi is a small state."
        with pytest.raises(AugmentationException, match='Input too small'):
            QuestionGenerator.generate(text)


class TestWebsiteScrapper:

    @responses.activate
    def test_web_scrapper(self):
        WebScraper.max_pages_allowed = 1
        url = 'http://localhost.kairon.local'
        with open("tests/testing_data/augmentation/scraper_test_data.txt", "r", encoding='latin-1') as file:
            html1 = file.read()
        responses.add(
            responses.GET,
            'http://localhost.kairon.local',
            status=200,
            body=html1
        )
        responses.add(
            responses.GET,
            'http://localhost.kairon',
            status=200,
            body=''
        )
        max_pages = 2
        pages = WebScraper.scrape_pages(url, max_pages)
        assert pages[0]['url']
        assert pages[0]['text']

    @responses.activate
    def test_web_scrapper_invalid_url(self):
        url = 'http://localhost.kairon.local'
        max_pages = 2
        pages = WebScraper.scrape_pages(url, max_pages)
        assert len(pages) == 0

    def test_web_scrapper_pages_less_than_equal_to_0(self):
        url = 'http://localhost.kairon.local'
        max_pages = -1
        pages = WebScraper.scrape_pages(url, max_pages)
        assert len(pages) == 0

    def test_join_bulletins_one_parent_and_two_bulletins(self):
        test_input = ['parent', '-bulletin1', '-bulletin2']
        expected = ['parent -bulletin1 -bulletin2']
        actual = WebScraper.join_bulletins(test_input)
        assert actual[0] == expected[0]

    def test_join_bulletins_no_bulletins(self):
        test_input = ['text1', 'text2']
        expected = ['text1', 'text2']
        actual = WebScraper.join_bulletins(test_input)
        assert actual == expected

    def test_join_bulletins_parent_bulletin(self):
        test_input = ['parent', '-bulletin1', 'text']
        expected = ['parent -bulletin1', 'text']
        actual = WebScraper.join_bulletins(test_input)
        assert actual == expected

    def test_remove_headers_and_seprate_headers_joined_with_regular_text(self):
        with open(
                "tests/testing_data/augmentation/scraper_test_data_2.txt",
                "r", encoding='latin-1') as file:
            html = file.read()
        soup = BeautifulSoup(html, 'html.parser')
        input_list = ['Free and open stock market and financial education',
                      'Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.',
                      'Modules',
                      '1. Introduction to Stock Markets15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.',
                      '2. Technical Analysis22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.',
                      '3. Fundamental Analysis16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.',
                      '4. Futures Trading13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc',
                      '5. Options Theory for Professional Trading25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.',
                      '6. Option Strategies14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.',
                      '7. Markets and Taxation7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.',
                      '8. Currency, Commodity, and Government Securities19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.',
                      '9. Risk Management & Trading Psychology16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading',
                      '10. Trading Systems16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.',
                      '11. Personal Finance (Part 1)30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.',
                      '12. Innerworth Mind over markets603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.',
                      '13. Integrated Financial Modelling9 chapters', 'Finance made easy for kids',
                      'A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.',
                      'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.',
                      'Chapter updates - 5. Options Theory for Professional Trading on November 29, 2021',
                      'Ch 25 Options M2M and P&L calculation',
                      '25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021',
                      'Ch 9 Debt Schedule',
                      '9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021',
                      'Ch 30 Basics of Macro Economics',
                      '30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020',
                      'Ch 26 The Mutual Fund Portfolio',
                      '26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020',
                      'Ch 25 How to analyze a debt mutual fund?',
                      '25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..',
                      'Recent comments', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021',
                      'Good luck, Yashwanth. ...17 Dec 2021', "Don't have a Zerodha account?",
                      'Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account']
        expected = [[
            'Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.'],
            [
                '1. Introduction to Stock Markets 15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.'],
            [
                '2. Technical Analysis 22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.'],
            [
                '3. Fundamental Analysis 16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.'],
            [
                '4. Futures Trading 13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc'],
            [
                '5. Options Theory for Professional Trading 25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.'],
            [
                '6. Option Strategies 14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.'],
            [
                '7. Markets and Taxation 7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.'],
            [
                '8. Currency, Commodity, and Government Securities 19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.'],
            [
                '9. Risk Management & Trading Psychology 16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading'],
            [
                '10. Trading Systems 16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.'],
            [
                '11. Personal Finance (Part 1) 30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.'],
            [
                '12. Innerworth Mind over markets 603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.'],
            ['13. Integrated Financial Modelling 9 chapters'], [
                'A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.',
                'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.'],
            ['Chapter updates  - 5. Options Theory for Professional Trading on November 29, 2021'], [
                '25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021'],
            [
                '9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021'],
            [
                '30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020'],
            [
                '26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020'],
            [
                '25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..'],
            ['...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021',
             'Good luck, Yashwanth. ...17 Dec 2021'],
            ['Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account']]
        actual = WebScraper.remove_headers_and_separate_headers_joined_with_regular_text(input_list, soup)
        assert expected == actual

    def test_fix_incomplete_text_and_add_left_out_p_tags(self):
        with open("tests/testing_data/augmentation/scraper_test_data_2.txt", "r", encoding='latin-1') as file:
            html = file.read()
        soup = BeautifulSoup(html, 'html.parser')
        input_list = [
            'Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.',
            '1. Introduction to Stock Markets 15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.',
            '2. Technical Analysis 22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.',
            '3. Fundamental Analysis 16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.',
            '4. Futures Trading 13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc',
            '5. Options Theory for Professional Trading 25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.',
            '6. Option Strategies 14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.',
            '7. Markets and Taxation 7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.',
            '8. Currency, Commodity, and Government Securities 19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.',
            '9. Risk Management & Trading Psychology 16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading',
            '10. Trading Systems 16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.',
            '11. Personal Finance (Part 1) 30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.',
            '12. Innerworth Mind over markets 603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.',
            '13. Integrated Financial Modelling 9 chapters',
            'A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.',
            'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.',
            'Chapter updates  - 5. Options Theory for Professional Trading on November 29, 2021',
            '25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021',
            '9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021',
            '30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020',
            '26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020',
            '25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..',
            '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021',
            'Good luck, Yashwanth. ...17 Dec 2021',
            'Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account']
        expected = [[
                        'Varsity is an extensive and in-depth collection of stock market and financial lessons created by Karthik Rangappa at Zerodha. It is openly accessible to everyone and is one of the largest financial education resources on the web.'],
                    [
                        '1. Introduction to Stock Markets  15 chaptersInvesting ensures financial security, and the Stock market plays a pivotal role in this domain, it is a place where people buy/sell shares of publicly listed companies. In this module, you will learn about the fundamentals of the stock market, how to get started, how it functions and the various intermediaries that appertain it.'],
                    [
                        '2. Technical Analysis  22 chaptersTechnical Analysis (TA) plays an important role in developing a point of view. Like every other research, TA also has its own attributes. In this module, we will discover all those complex attributes of TA, study various patterns, indicators and theories that will help you as a trader to find upright trading opportunities in the market.'],
                    [
                        '3. Fundamental Analysis  16 chaptersFundamental Analysis (FA) is a holistic approach to study a business. If you are an investor that is looking for long term investments this module will help you understand Equity research, help you in reading the financial statements, annual reports, calculation of Financial Ratio, Analysis and most importantly help you in evaluating the intrinsic value of a stock to find long-term investing opportunities.'],
                    [
                        '4. Futures Trading  13 chaptersFutures Trading involves trading in contracts in the derivatives markets. This module covers the various intricacies involved in undergoing a futures trade including margins, leverages, pricing, etc'],
                    [
                        '5. Options Theory for Professional Trading  25 chaptersAn option is a contract where the price of the options is based on an underlying. Options contracts grant the buyer the right to buy the underlying without a compulsory obligation.'],
                    [
                        '6. Option Strategies  14 chaptersThe module covers various options strategies that can be built with a multi-dimensional approach based on Market trend involving Option Greeks, Risk-Return, etc.'],
                    [
                        '7. Markets and Taxation  7 chaptersAs a trader in India, you should be informed of all the taxes that are levied on your investments and account. This module overlays the taxation countenance of Investing/Trading in the Markets. It also outlines the various essential topics like calculation of your turnover, how to prepare a balance sheet and the P&L statement, and further about how you can file your Income Tax Returns.'],
                    [
                        '8. Currency, Commodity, and Government Securities  19 chaptersThis module covers the Currency, MCX Commodity contract, and the Government Securities (GSec) traded in the Indian Markets.'],
                    [
                        '9. Risk Management & Trading Psychology  16 chaptersThe module covers the risk management aspect along with the psychology required for being consistent and profitable while trading'],
                    [
                        '10. Trading Systems  16 chaptersHave you considered building your own Trading System? Well, then this module is for you. The major components of building a good trading system are input parameters and interpreting output alongside decision-making. In this module, we will learn about all the components and much more including the techniques and different types of Trading Systems.'],
                    [
                        '11. Personal Finance (Part 1)  30 chaptersPersonal finance is an essential aspect of your financial life as it helps you achieve your short term and long term financial goals. This module encompasses the various aspects of personal finance such as retirement planning, Mutual funds, ETFs, Bonds, and goal-oriented investments.'],
                    [
                        '12. Innerworth Mind over markets  603 chaptersA series of articles on the psychology of trading, that will guide you mend your thought and prepare you psychologically to become a novice trader.'],
                    ['13. Integrated Financial Modelling  9 chapters',
                     'A box set of 5 books introducing 5 financial concepts to children. Brought to you by Varsity @ Zerodha.',
                     'Where does money come from and where does it go? The innocent inquisitiveness of children is what makes them most endearing. Help your little ones understand the financial world through simple stories that make learning fun.'],
                    ['Chapter updates   - 5. Options Theory for Professional Trading on November 29, 2021',
                     '25.1 Back to Futures After many years, Im updating this module with a new chapter, and it still feels as if I wrote this module on options just yesterday. Thousands of queries have poured i .. - 13. Integrated Financial Modelling on November 19, 2021',
                     '9.1 Dealing with debt We dealt with fixed assets in the previous chapter. The fixed assets, as you realize, is the most oversized line item on the asset side of the balance sheet. In this chapter, .. - 11. Personal Finance (Part 1) on February 25, 2021',
                     '30.1 Why macroeconomics? The module on Personal Finance has come a long way with over 30 chapters. I can easily think of another 10 or 15 chapters to add, but I wont do that I think we .. - 11. Personal Finance (Part 1) on December 24, 2020',
                     '26.1 Assumptions We have reached a stage where we have discussed almost everything related to Mutual funds, leaving us with the last crucial bit, i.e. the mutual fund portfolio construction. Iv .. - 11. Personal Finance (Part 1) on November 23, 2020',
                     '25.1 Confused Portfolio In the previous chapter, we picked up an equity fund (Kotak Standard Multi cap Fund) and looked at the steps to analyze and Equity fund. The idea was to highlight the steps ..',
                     '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021', '...17 Dec 2021',
                     'Good luck, Yashwanth. ...17 Dec 2021',
                     'Excellent platforms / Free equity investments / Flat 20 intraday and F&O tradesOpen an account']]
        actual = WebScraper.remove_headers_and_separate_headers_joined_with_regular_text(input_list, soup)
        assert expected == actual


class TestWebsiteQnAGenerator:

    @responses.activate
    def test_website_qna_generator(self):
        expected = ['what is kairon?',
                    'what does kairon do?',
                    "what is kairon's focus?",
                    'what does kairon focus on?',
                    'what does kairon aim to provide?'
                    'what is kairon built on?'
                    'what does kairon focus on?']
        url = 'http://localhost.kairon.local'
        with open("tests/testing_data/augmentation/scraper_test_data.txt", "r", encoding='latin-1') as file:
            html1 = file.read()
        responses.add(
            responses.GET,
            url,
            status=200,
            body=html1
        )
        actual = []
        response = WebsiteQnAGenerator.get_qa_data(url, 2)
        for i in response:
            actual.extend(i['training_examples'])
        print(response)
        assert any(text.lower() in expected for text in actual)

    @responses.activate
    def test_website_qna_generator_invalid_url(self):
        url = 'http://localhost.kairon.local'
        response = WebsiteQnAGenerator.get_qa_data(url, 2)
        assert len(response) == 0

    def test_website_qna_generator_pages_less_than_equal_to_0(self):
        url = 'http://localhost.kairon.local'
        max_pages = 0
        response = WebsiteQnAGenerator.get_qa_data(url, max_pages)
        assert len(response) == 0
