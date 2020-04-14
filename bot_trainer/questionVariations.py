import nltk
from nltk.corpus import wordnet
from nltk.stem import WordNetLemmatizer
import re
import gensim
from autocorrect import Speller
from nltk.tokenize import TweetTokenizer

tknzr = TweetTokenizer()
lemmatizer = WordNetLemmatizer()
spell = Speller(lang="en")
elim = ["DT", "PRP", "PRP$"]

entity_helpverb_words = [
    "digite",
    "agile",
    "am",
    "is",
    "are",
    "was",
    "were",
    "being",
    "been",
    "be",
    "for",
    "swiftly",
    "in",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "im",
    "there",
    "here",
    "on",
    "or",
    "how",
    "of",
    "where",
    "when",
    "may",
    "might",
    "must",
    "can",
    "could",
    "the",
    "swiftalm",
    "swift",
    "kanban",
    "alm",
    "sap",
    "cloud",
    "scrum",
    "jira",
    "to",
    "mnc",
    "with",
    "not",
    "i",
    "what",
    "why",
]

m = gensim.models.KeyedVectors.load_word2vec_format(
    "./pretrained_model/wiki-news-300d-1M.vec"
)  # enter the load path of model


class Variate:
    def get_wordnet_pos(self, word):
        """Map POS tag to first character lemmatize() accepts"""
        tag = nltk.pos_tag([word])[0][1][0].upper()
        tag_dict = {
            "J": wordnet.ADJ,
            "N": wordnet.NOUN,
            "V": wordnet.VERB,
            "R": wordnet.ADV,
        }

        return tag_dict.get(tag, wordnet.NOUN)

    def filt_func(self, list1):
        list2 = []
        for word2 in list1:
            word3 = word2.strip()
            word4 = re.sub("[^a-zA-Z]+", "", str(word3))
            word4 = word4.lower()
            word6 = spell(word4)
            list2.append(word6)
        list3 = list(set(list2))
        return list3

    def preprocess_text(
        self,
        text,
        custom_stopwords,
        word_len,
        white_space=True,
        lower_case=True,
        number=True,
    ):
        list_lemmatized_words = []
        filtered_tokens = []

        text = str(text)
        # removing white spaces from the both end of the text.
        if white_space == True:
            text = text.strip()
        if lower_case == True:
            text = text.lower()  # converting to the lower case.
        if number == True:
            text = re.sub(
                "[^a-zA-Z|']+", " ", str(text)
            )  # Removing numbers from the text.

        token1 = tknzr.tokenize(text)
        for word in token1:
            list_lemmatized_words.append(word)

        filtered_tokens = [
            w
            for w in list_lemmatized_words
            if len(w) > word_len and not w in custom_stopwords
        ]
        return filtered_tokens

    def comb(self, lis):
        allQ = []
        word_dictionary = dict()
        for sent in lis:
            testr = self.preprocess_text(
                sent,
                entity_helpverb_words,
                0,
                white_space=True,
                lower_case=True,
                number=True,
            )
            testf = self.preprocess_text(
                sent, [], 0, white_space=True, lower_case=True, number=True
            )
            # making word dictionary
            tagged = nltk.pos_tag(testr)
            tag1 = [i[0] for i in tagged if i[1] not in elim]

            for word1 in tag1:
                try:
                    d = m.most_similar(word1, topn=10)
                    listw = []
                    for asd in d:
                        listw.append(asd[0])
                    list_middle = self.filt_func(listw)
                    #####################################################################
                    dag = lemmatizer.lemmatize(word1, self.get_wordnet_pos(word1))
                    rd = []
                    for ag in list_middle:
                        if lemmatizer.lemmatize(ag, self.get_wordnet_pos(ag)) != dag:
                            rd.append(ag)
                    ####################################################################
                    word_dictionary[word1] = rd
                except:
                    pass

            # generate questions
            collective = []
            for i in range(10):
                listl = []
                for word in testf:
                    try:
                        listab = word_dictionary[word]
                        listl.append(listab[i])
                    except:
                        listl.append(word)
                collective.append(listl)

            collective2 = []
            for entity in collective:
                collective2.append(" ".join(entity))
            collective2 = list(set(collective2))
            allQ = allQ + collective2
        for sent1 in allQ:
            if sent1 in lis:
                allQ.remove(sent1)
        return allQ
