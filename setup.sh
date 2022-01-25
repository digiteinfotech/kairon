#!/bin/bash
python -m pip install pip==20.2.4
python -m pip install -r requirements.txt
python -m spacy download en_core_web_md
python -m spacy link en_core_web_md en
python -m nltk.downloader wordnet
python -m nltk.downloader averaged_perceptron_tagger
python -m nltk.downloader punkt
python -m nltk.downloader stopwords
python -m nltk.downloader omw-1.4