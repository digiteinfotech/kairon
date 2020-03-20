from nltk.corpus import wordnet
import spacy
import gensim
from sentence_transformers import SentenceTransformer
import itertools
from scipy.spatial.distance import cosine

class QuestionGeneration:

    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
        self.sentence_transformer = SentenceTransformer('./pretrained_model/bert-large-nli-mean-tokens')
        self.fastText = gensim.models.KeyedVectors.load_word2vec_format('./pretrained_model/wiki-news-300d-1M.vec')

    def get_synonyms( self, text: str):
        tokens = [ doc.text  for doc in self.nlp(text) if not doc.is_punct and not doc.is_stop and not doc.is_quote]
        token_list = {}
        for token in tokens:
            for syn in wordnet.synsets(token):
                synonyms = set()
                for l in syn.lemmas():
                    synonyms.add(l.name())
                if synonyms.__len__() > 0:
                    token_list[token] = list(synonyms)
        return token_list

    def get_synonyms_fastText( self, text: str):
        tokens = [ doc.text  for doc in self.nlp(text) if not doc.is_punct and not doc.is_stop and not doc.is_quote]
        token_list = {}
        for token in tokens:
            try:
                similar_words = self.fastText.most_similar(token, topn=10)
                synonyms = set()
                for word, similarity in similar_words:
                    synonyms.add(word)
                if synonyms.__len__() > 0:
                    token_list[token] = list(synonyms)
            except:
                print()
        return token_list

    def checkDistance(self, source, target):
        return 1 - cosine(source, target)

    async def generateQuestions(self ,texts):
        result = []
        if type(texts) == str:
            texts = [texts]
        text_encodings = self.sentence_transformer.encode(texts)
        for i in range(len(texts)):
            text = texts[i]
            text_encoding = text_encodings[i]
            synonyms = self.get_synonyms_fastText(text)
            tokens = [synonyms[doc.text] if doc.text in synonyms.keys() else [doc.text] for doc in self.nlp(text)]
            questions = [' '.join(question) for question in list(itertools.product(*tokens))]
            questions_encodings = self.sentence_transformer.encode(questions)
            questions = [ questions[i] for i in range(len(questions)) if self.checkDistance(text_encoding, questions_encodings[i]) > 0.90 ]
            #questions = filter( lambda x: self.checkDistance(text_encoding, x) >= 0.90  , questions)
            if len(questions):
                result.extend(list(questions))
        return result


#question = QuestionGeneration()
#text = "where is digite located?"
#questions_gen = question.generateQuestions(text)

