from nltk.corpus import wordnet
import spacy
import gensim
from sentence_transformers import SentenceTransformer
import itertools
from scipy.spatial.distance import cosine

class QuestionGenerator:
    nlp = spacy.load("en_core_web_sm")
    sentence_transformer = SentenceTransformer('bert-large-nli-stsb-mean-tokens')
    fastText = None#gensim.models.KeyedVectors.load_word2vec_format('./pretrained_model/wiki-news-300d-1M.vec')

    @staticmethod
    def get_synonyms(text: str):
        tokens = [ doc.text  for doc in QuestionGenerator.nlp(text) if not doc.is_punct and not doc.is_stop and not doc.is_quote]
        token_list = {}
        for token in tokens:
            for syn in wordnet.synsets(token):
                synonyms = set()
                for l in syn.lemmas():
                    synonyms.add(l.name())
                if synonyms.__len__() > 0:
                    token_list[token] = list(synonyms)
        return token_list

    @staticmethod
    def get_synonyms_fastText(text: str):
        tokens = [ doc.text  for doc in QuestionGenerator.nlp(text) if not doc.is_punct and not doc.is_stop and not doc.is_quote]
        token_list = {}
        for token in tokens:
            try:
                similar_words = QuestionGenerator.fastText.most_similar(token, topn=10)
                synonyms = set()
                for word, similarity in similar_words:
                    synonyms.add(word)
                if synonyms.__len__() > 0:
                    token_list[token] = list(synonyms)
            except:
                print()
        return token_list

    @staticmethod
    def checkDistance(source, target):
        return 1 - cosine(source, target)

    @staticmethod
    async def generateQuestions(texts):
        result = []
        if type(texts) == str:
            texts = [texts]
        text_encodings = QuestionGenerator.sentence_transformer.encode(texts)
        for i in range(len(texts)):
            text = texts[i]
            text_encoding = text_encodings[i]
            synonyms = QuestionGenerator.get_synonyms(text)
            tokens = [synonyms[doc.text] if doc.text in synonyms.keys() else [doc.text] for doc in QuestionGenerator.nlp(text)]
            questions = [' '.join(question) for question in list(itertools.product(*tokens))]
            questions_encodings = QuestionGenerator.sentence_transformer.encode(questions)
            questions = [ questions[i] for i in range(len(questions)) if QuestionGenerator.checkDistance(text_encoding, questions_encodings[i]) > 0.90 ]
            if len(questions):
                if len(questions) == 1 and text[i] == questions[0]:
                    continue
                result.extend(list(questions))
        return result