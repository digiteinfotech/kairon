#!/bin/bash
python3.10 -m pip install -r requirements/dev.txt
python3.10 -m spacy download en_core_web_md
python3.10 -m spacy link en_core_web_md en
python3.10 -m nltk.downloader averaged_perceptron_tagger
python3.10 -m nltk.downloader punkt
python3.10 -m nltk.downloader stopwords
python3.10 -m nltk.downloader omw-1.4
python3.10 -m nltk.downloader wordnet