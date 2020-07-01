#!/bin/bash
python3.6 -m pip install --upgrade pip
python3.6 -m pip install -r requirements.txt
python3.6 -m spacy download en_core_web_md
python3.6 -m spacy link en_core_web_md en
python3.6 -m nltk.downloader wordnet
python3.6 -m nltk.downloader averaged_perceptron_tagger