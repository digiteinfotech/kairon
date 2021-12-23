from loguru import logger

import nltk
import trafilatura
from bs4 import BeautifulSoup
from urllib.request import Request, urlopen

class WebScraper():
    """Class is used to crawl and extract text from webpages"""
    
    max_pages_allowed = 20

    @staticmethod
    def clean_headers(s: str):
        
        """
        This function remove non ascii characters and extra white spaces from the text
        
        :param s: input text
        :return: cleaned text
        """
        
        s = "".join(i for i in s if ord(i) < 128)
        s = s.replace("\n"," ")
        s = s.split()
        s = " ".join(s)
        return s
    
    @staticmethod
    def join_bulletins(text: list):

        """
        This function join bulletins with there parent by combining them in a single string.

        :param text: list of strings of meaningful text extracted from website
        :return: a list of strings of text from the website
        """

        better_text = [text[0]]
        for i in range(1,len(text)):
            if text[i][0] == '-': #bulletins have '-' as the first character in the string. They are appended in the last added string in list better_text
                better_text[-1] = better_text[-1] + " "+WebScraper.clean_headers(text[i])
            else:
                better_text.append(WebScraper.clean_headers(text[i]))
        
        return better_text
    
    @staticmethod
    def remove_headers_and_seprate_headers_joined_with_regular_text(text: str,soup):
        
        """
        This function removes strings which are headers in the web page from the extracted text.
        Also it groups all the children(which are not headers) of the headers together as a list of strings.
        Some headers get mixed with text so it also separates them from the strings.
        These mixed headers are added in the same string in the beginning only.

        :param text: list of meaningful text extracted from website
        :param soup: soup of extracted HTML
        :return: a list of list of strings of text from the website 
        """
        all_header_text = set() #a set to store all headers
        htags = ['h1','h2','h3','h4','h5','h6','h7','h8','h9','h10']
        #extract all headers from soup
        for htag in htags:
            for ht in soup.find_all(htag):
                cleaned_text = WebScraper.clean_headers(ht.text)
                if len(cleaned_text) !=0:
                    all_header_text.add(cleaned_text)

        better_text = [[]] #a list to store text in orderly manner
        for i in text:
            if i in all_header_text:
                better_text.append([]) #appends an empty list
            elif any([j for j in all_header_text if j in i]): #if any of the header is in 'i' then this condition is satisfied
                candidate = "" #to store string of header present in 'i'
                good = False #if True then 'i' have a header in the beginning
                for j in all_header_text:
                    if j in i:
                        tmp_ls = i.split(j)
                        if len(tmp_ls[0]) == 0 and len(tmp_ls)!=0: #if the first element of tmp_ls is of len=0 then a header was present in the beginning
                            good = True
                            candidate = candidate if len(candidate) > len(j) else j #to store the biggest matching header in candidate

                if good:
                    better_text.append([candidate+" "+i.replace(candidate,"",1)])
                else:
                    better_text[-1].append(i)
            else:
                better_text[-1].append(i)
        return [i for i in better_text if len(i)!=0] # remove empty lists
        
    @staticmethod
    def fix_incomplete_text_and_add_left_out_p_tags(text: str,soup):
        
        """
        This function fixes incomplete sentences and also add ptags data from soup
        that are not yet added in text

        :param text: list of list of strings
        :param soup: soup of extracted HTML
        :return: a list of list of strings of text from the website which is also have missing ptags data
        """
        better_text = []
        not_select_ps = set() #ptags not to select
        for i in range(len(text)):
            nm = [] #a list to store strings
            k = 0
            while k < len(text[i]): #iterates current text
                t = text[i][k]
                if len(nm)!= 0:
                    toks = nltk.sent_tokenize(nm[-1]) #splits last string stored in nm into sentences
                    #if last sentence is not complete and also not a bulletin then add t in last sentence of nm
                    if toks[-1][-1] not in ['.','?','!']  and "-" not in toks[-1]:
                        toks[-1] = toks[-1] + " "+t
                        nm[-1] = " ".join(toks)
                    else:
                        nm.append(" ".join(t.split()))
                else:
                    nm.append(" ".join(t.split()))
                k+=1
            not_select_ps.add(" ".join(nm)) #add current nm in not_select_ps
            better_text.append(nm)

        p_tags_data = [] #a list to store unselected ptags data
        for para in soup.find_all("p"):
            cleaned_p = WebScraper.clean_headers(para.get_text())
            if len(nltk.sent_tokenize(cleaned_p))>2: #if number of sentences in current ptag is greater than 2
                flag=True
                #some of the ptags can be incomplete so using a for loop to check
                for p in not_select_ps:
                    if cleaned_p in p:
                        flag=False
                        break
                if flag:
                    p_tags_data.append(cleaned_p)

        if len(p_tags_data)!=0:
            better_text.append(p_tags_data)
        
        return better_text

        
    @staticmethod
    def get_text(url: str,pages: list,max_pages: int):
        
        """
        This function extract text from webpages and append them in the variable pages
        
        :param url: url from which to extract text
        :param pages: list of all the pages extracted so far
        :param max_pages: maximum number of pages to extract
        :return: List of links of children of current page and a boolean(True means continue crawling)
        """
        
        try:
            page = {"url": url,
               "type": "qna" if "faq" in url or "qna" in url else "normal",
               "text" : None}
            agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36\
            (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'

            request = Request(url, headers={'User-Agent': agent})

            HTML = urlopen(request).read().decode() #get html of current page

            soup = BeautifulSoup(HTML, 'html.parser') #creates a soup of current page
            text = trafilatura.extract(HTML,include_comments=False,include_tables=False,include_links=False,target_language='en') #extract relevant text from current page
            text = text.replace("READ MORE","")
            text = text.replace("LEARN MORE","")
            text = text.split("\n")
            text = WebScraper.join_bulletins(text)
            text = WebScraper.remove_headers_and_seprate_headers_joined_with_regular_text(text,soup)
            text = WebScraper.fix_incomplete_text_and_add_left_out_p_tags(text,soup)
            page['text'] = text
            pages.append(page)

            if len(pages) < max_pages: #to check if maximum page required is reached
                links = [] #to store child links of current page
                for line in soup.find_all('a'):
                    try:
                        if "https" in line.get('href'):
                            links.append(line.get('href'))
                    except Exception as ex:
                        logger.exception("Exception in WebScraper when extracting links - {}".format(ex))
                return links,False
            else:
                return [],True
        except Exception as ex:
            logger.exception("Exception in WebScraper url: {} - exception: {}".format(url,ex))
            return [],False

    @staticmethod
    def scrape_pages(url: str,max_pages: int):
        
        """
        This function is used to crawl a website
        
        :param url: url of website
        :param max_pages: maximum number of pages to extract
        :return: List of links of children of current page and a boolean(True means continue scraping)
        """
        
        if max_pages <=0: #if max_pages less than equal to zero then an empty list is returned
            return []
        pages = [] #all the extracted pages data will be stored in this variable
        visited = set() #maintains a set of urls visited so far to avoid entering a cycle while crawling
        queue = [] #a queue to store links to scrape during BFS traversal
        queue.append(url)
        visited.add(url)
        max_pages = min(max_pages,WebScraper.max_pages_allowed)
        #start web crawling via BFS traversal
        while queue:
            childern,limit_reached = WebScraper.get_text(queue[0],pages,max_pages)
            queue.pop(0)
            if not limit_reached: #if maxmimum limit is not reached continue crawling
                for c in childern:
                    if c not in visited:
                        queue.append(c)
                        visited.add(c)
            else: #stop crawling as maxmimum limit is reached
                break
        return pages