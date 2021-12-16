import nltk
import trafilatura
from bs4 import BeautifulSoup
from urllib.request import Request, urlopen
from lxml import html

class WEB_SCRAPPER():
    MAX_PAGES_ALLOWED = 20
    
    @staticmethod
    def clean_text(s):
        s = "".join(i for i in s if ord(i) < 128)
        return s
    
    @staticmethod
    def clean_headers(s):
        s = "".join(i for i in s if ord(i) < 128)
        s = s.replace("\n"," ")
        s = s.split()
        s = " ".join(s)
        return s
    
    @staticmethod
    def get_text(url,pages,maxPages):
        """
        extract text from url and adds append it in pages
        :param url: url from which to extract text
        :param pages: list of all the pages extracted so far
        """
        try:
            page = {"url": url,
               "type": "qna" if "faq" in url or "qna" in url else "normal",
               "text" : None}
            agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36\
            (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'

            request = Request(url, headers={'User-Agent': agent})

            HTML = urlopen(request).read().decode()

            soup = BeautifulSoup(HTML, 'html.parser')
            text = trafilatura.extract(HTML,include_comments=False,include_tables=False,include_links=False,target_language='en')
            text = text.replace("READ MORE","")
            text = text.replace("LEARN MORE","")
            text = text.split("\n")
            mask1 = [text[0]]
            for i in range(1,len(text)):
                if text[i][0] == '-':
                    mask1[-1] = mask1[-1] + " "+WEB_SCRAPPER.clean_headers(text[i])
                else:
                    mask1.append(WEB_SCRAPPER.clean_headers(text[i]))

            all_header_text = set()
            htags = ['h1','h2','h3','h4','h5','h6','h7','h8','h9','h10'] 
            for htag in htags:
                for ht in soup.find_all(htag):
                    cleaned_text = WEB_SCRAPPER.clean_headers(ht.text)
                    if len(cleaned_text) !=0:
                        all_header_text.add(cleaned_text)

            mask2 = [[]]
            for i in mask1:
                if i in all_header_text:
                    mask2.append([])
                elif any([j for j in all_header_text if j in i]):
                    candidate = ""
                    good = False
                    for j in all_header_text:
                        if j in i:
                            tmpLs = i.split(j)
                            if len(tmpLs[0]) == 0 and len(tmpLs)!=0:
                                good = True
                                candidate = candidate if len(candidate) > len(j) else j

                    if good:
                        mask2.append([candidate+" "+i.replace(candidate,"",1)])
                    else:
                        mask2[-1].append(i)
                else:
                    mask2[-1].append(i)
            mask2 = [i for i in mask2 if len(i)!=0]

            mask3 = []
            not_select_ps = set()
            for i in range(len(mask2)):
                nm = []
                k = 0
                while k < len(mask2[i]):
                    t = mask2[i][k]
                    if len(nm)!= 0:
                        toks = nltk.sent_tokenize(nm[-1])
                        if toks[-1][-1] not in ['.','?','!']  and "-" not in toks[-1]:
                            toks[-1] = toks[-1] + " "+t
                            nm[-1] = " ".join(toks)
                        else:
                            nm.append(" ".join(t.split()))
                    else:
                        nm.append(" ".join(t.split()))
                    k+=1
                not_select_ps.add(" ".join(nm))
                mask3.append(nm)

            p_tags_data = []
            for para in soup.find_all("p"):
                cleaned_p = WEB_SCRAPPER.clean_headers(para.get_text())
                if cleaned_p not in not_select_ps and len(nltk.sent_tokenize(cleaned_p))>2:
                    p_tags_data.append(cleaned_p)

            if len(p_tags_data)!=0:
                mask3.append(p_tags_data)

            page['text'] = mask3
            pages.append(page)

            if len(pages) < maxPages:
                links = []
                for line in soup.find_all('a'):
                    try:
                        if "https" in line.get('href'):
                            links.append(line.get('href'))
                    except:
                        pass
                return links,False
            else:
                return [],True
        except:
            return [],False

    @staticmethod
    def scrape_pages(url,maxPages):
        if maxPages <=0:
            return []
        pages = []
        visited = set()
        queue = []
        queue.append(url)
        visited.add(url)
        maxPages = min(maxPages,WEB_SCRAPPER.MAX_PAGES_ALLOWED)
        while queue:
            childern,LIMIT_REACHED = WEB_SCRAPPER.get_text(queue[0],pages,maxPages)
            queue.pop(0)
            if not LIMIT_REACHED:
                for c in childern:
                    if c not in visited:
                        queue.append(c)
            else:
                break
        return pages