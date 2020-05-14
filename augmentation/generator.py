import itertools
from string import punctuation

import gensim.downloader as api
import spacy
from scipy.spatial.distance import cosine
from sentence_transformers import SentenceTransformer


class QuestionGenerator:
    nlp = spacy.load("en_core_web_sm")
    sentence_transformer = SentenceTransformer('bert-large-nli-stsb-mean-tokens')
    model = api.load('word2vec-google-news-300')
    punct_token = set(punctuation)

    @staticmethod
    def get_synonyms_from_embedding(text: str):
        tokens = [doc.text for doc in QuestionGenerator.nlp(text)
                  if not doc.is_punct and not doc.is_stop and not doc.is_quote]
        token_list = {}
        for token in tokens:
            try:
                similar_words = QuestionGenerator.model.most_similar(token, topn=10)
                synonyms = set([str(word).lower().replace("_", " ") for word, similarity in similar_words if similarity >= 0.60])
                if synonyms.__len__() > 0:
                    token_list[token] = list(synonyms)
            except KeyError:
                pass
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
            synonyms = QuestionGenerator.get_synonyms_from_embedding(text)
            tokens = [synonyms[doc.text] if doc.text in synonyms.keys() else [doc.text] for doc in QuestionGenerator.nlp(text)]
            questions = [''.join(w if set(w) <= QuestionGenerator.punct_token else ' '+w for w in question).strip() for question in list(itertools.product(*tokens))]
            questions_encodings = QuestionGenerator.sentence_transformer.encode(questions)
            questions = [ questions[i] for i in range(len(questions)) if QuestionGenerator.checkDistance(text_encoding, questions_encodings[i]) > 0.70 ]
            if len(questions):
                if len(questions) == 1 and text[i] == questions[0]:
                    continue
                result.extend(list(questions))
        return list(set(result) - set(texts))