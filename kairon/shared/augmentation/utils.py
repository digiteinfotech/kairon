from typing import Text

import numpy as np
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer, util
from itertools import chain
from nlpaug.augmenter.char import KeyboardAug
from nlpaug.augmenter.word import SynonymAug
from nlpaug.flow import Sometimes
from nlpaug.augmenter.word import SpellingAug
from nlpaug.augmenter.word import AntonymAug


class AugmentationUtils:

    similarity_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    kw_model = KeyBERT()

    @staticmethod
    def augment_sentences_with_errors(sentences: list, stopwords: list = None, num_variations: int = 5):
        """
        Generates augmented data with keyboard and spelling errors along with antonym and
        synonyms of words in the sentences passed.

        :param sentences: list of sentences to augment.
        :param stopwords: stopwords which should not be modified.
        :param num_variations: number of sentences to generate.
        """
        keyboard_aug = KeyboardAug(
            aug_char_min=1, aug_char_max=1, aug_word_p=0.2, stopwords=stopwords,
            include_special_char=False, include_numeric=False, include_upper_case=True, min_char=4
        )
        synonym_aug = SynonymAug(aug_src='wordnet', aug_p=0.2, stopwords=stopwords)
        antonym_aug = AntonymAug(aug_p=0.2, stopwords=stopwords)
        spelling_aug = SpellingAug(aug_p=0.2, stopwords=stopwords, include_reverse=False)

        aug = Sometimes([keyboard_aug, synonym_aug, spelling_aug, antonym_aug])
        augmented_text = aug.augment(sentences, n=num_variations)
        augmented_text = list(chain.from_iterable(augmented_text))
        return set(augmented_text)

    @staticmethod
    def generate_synonym(entity: str, num_variations: int = 3):
        """
        Generates synonyms for entity passed.

        :param entity: entity for which synonym is needed.
        :param num_variations: number of sentences to generate.
        """
        from nltk.corpus import wordnet

        synonyms = []
        syn_sets = wordnet.synsets(entity)
        for syn in syn_sets:
            for word in syn.lemma_names():
                if word != entity:
                    synonyms.append(word)
                    num_variations -= 1
                if num_variations <= 0:
                    return synonyms
        return synonyms

    @staticmethod
    def get_similar(sentences: list, target: str, threshold: float):
        """
        Filters sentences which are similar to the target sentence.

        :param sentences: list of sentences that needs to be filtered.
        :param target: Text with which similarity needs to be determined.
        :param threshold: similarity threshold
        """
        embeddings1 = AugmentationUtils.similarity_model.encode(target, convert_to_tensor=True)
        embeddings2 = AugmentationUtils.similarity_model.encode(sentences, convert_to_tensor=True)

        cosine_scores = util.cos_sim(embeddings1, embeddings2)
        cosine_scores = np.asarray(cosine_scores[0], dtype=np.float)
        sentences = np.asarray(sentences, dtype=np.str)
        return sentences[cosine_scores > threshold].tolist()

    @staticmethod
    def get_keywords(paragraph: Text):
        key_tokens = AugmentationUtils.kw_model.extract_keywords(
            paragraph, keyphrase_ngram_range=(1, 3), stop_words='english', top_n=1
        )
        return key_tokens
