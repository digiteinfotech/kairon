from bs4 import BeautifulSoup
import requests
from loguru import logger as logging

from kairon.exceptions import AppException


class WebsiteParser:

    @staticmethod
    def data_preprocess(data):
        processed_data = ''
        for d in data:
            if d.isalpha():
                start_index = data.index(d)
                processed_data = data[start_index:] + '?'
                break

        return processed_data

    @staticmethod
    def check_word_count(qn):
        return len(qn.split(' '))

    @staticmethod
    def trunc_answer(ans, url):
        # truncate long answers and append read more hyperlink
        trunc_ans = " "
        ans_list = ans.split(' ')
        trunc_ans = trunc_ans.join(ans_list[:50])
        a_tag = f'<a target="_blank" href={url}> read more </a>'
        final_ans = trunc_ans + ' ... ' + a_tag
        return final_ans

    @staticmethod
    def get_context(url, soup):
        # add context to questions with less than 3 words
        h1 = soup.find_all('h1')
        if h1 and h1[0].text:
            context = h1[0].text
        else:
            url_components = [context for context in url.split('/') if context]
            context = url_components[-1].replace('-', ' ')
        return context

    @staticmethod
    def get_all_links(initial_url, depth=0):
        # extract all links from a web page
        all_links = [initial_url]

        if depth > 0:
            page = requests.get(initial_url)
            soup = BeautifulSoup(page.content, "html.parser")

            for a in soup.find_all('a'):
                try:
                    all_links.append(a['href'])
                except Exception as e:
                    logging.info(str(e))
                    continue
            return list(set(all_links))
        else:
            return all_links

    @staticmethod
    def is_valid_url(initial_url, url):
        # check the validity of a link
        if url == '' or url[0] == '/':
            url = initial_url + url
        elif url[0] == '#':
            url = initial_url + '/' + url
        try:
            if requests.get(url).status_code == 200:
                return url, True
        except Exception as e:
            logging.info(str(e))
        return url, False

    @staticmethod
    def get_qna_dict(qn_list, ans_list):
        # create QnA dict
        qn_dup_free = dict(zip(qn_list, ans_list))  # remove duplicate questions
        ans_dup_free = dict(zip(list(qn_dup_free.values()), list(qn_dup_free.keys())))  # remove duplicate answers
        final_qna_dict = {v: k for k, v in ans_dup_free.items()}  # final dict without duplicate qn and ans entries
        return final_qna_dict

    @staticmethod
    def remove_footer(soup):
        footer_len = len(soup.find_all('footer'))
        if footer_len:
            for _ in range(footer_len):
                if soup.footer:
                    soup.footer.decompose()
        return soup

    @staticmethod
    def get_qna(initial_url, depth=0):
        try:

            heading_tags = ["h1", "h2", "h3", "h4", "h5"]
            questions = []
            answers = []
            answer_citation = {}

            links = WebsiteParser.get_all_links(initial_url, depth)
            for link in links:
                url, is_valid_url = WebsiteParser.is_valid_url(initial_url, link)

                if is_valid_url:
                    page = requests.get(url)

                    soup = BeautifulSoup(page.content, "html.parser")
                    soup = WebsiteParser.remove_footer(soup)

                    for tag in soup.find_all(heading_tags):
                        if tag.text is None or tag.text == '':
                            continue
                        qn = WebsiteParser.data_preprocess(tag.text)
                        if qn == '':
                            continue
                        # add context if word size is less than 2"
                        if len(qn.split(' ')) < 3:
                            context = WebsiteParser.get_context(url, soup)
                            qn = context + ' ' + qn
                        next_tag = tag
                        ans = ''
                        # consider all paragraph texts between 2 headers as the answer for a given qn
                        for sibling in next_tag.find_next_siblings():
                            if sibling.name == "p":
                                ans = ans + sibling.text
                            elif sibling.name == 'ul':
                                li = sibling.find_all('li')
                                ul_text = ""
                                for ind, i in enumerate(li):
                                    ul_text = ul_text + '\n' + ' (' + str(ind + 1) + ') ' + i.text
                                ans = ans + ul_text + '\n'
                            else:
                                ans = ans + sibling.text
                        # truncate lengthy answers and leave a link
                        if len(ans):
                            questions.append(qn)
                            answers.append(ans)
                            answer_citation[ans] = url

            return WebsiteParser.get_qna_dict(questions, answers), answer_citation
        except Exception as e:
            logging.exception(e)
            raise AppException(
                f"Story suggestions isn't fully supported on this website yet. Failed with exception: {str(e)}")
