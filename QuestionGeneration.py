from nltk.corpus import wordnet
import spacy
from sentence_transformers import SentenceTransformer
import itertools
from scipy.spatial.distance import cosine

class QuestionGeneration:

    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
        self.sentence_transformer = SentenceTransformer('bert-large-nli-mean-tokens')

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

    def checkDistance(self, source, text):
        return 1 - cosine(source, self.sentence_transformer.encode([text])[0])

    def generateQuestions(self ,text: str):
        text_encoding = self.sentence_transformer.encode([text])[0]
        synonyms = self.get_synonyms(text)
        tokens = [synonyms[doc.text] if doc.text in synonyms.keys() else [doc.text] for doc in self.nlp(text)]
        questions = [' '.join(question) for question in list(itertools.product(*tokens))]
        questions = filter( lambda x: self.checkDistance(text_encoding, x) >= 0.90  , questions)
        return list(questions)

question = QuestionGeneration()
text = "where is digite located?"
questions_gen = question.generateQuestions(text)

