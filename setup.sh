#!/bin/bash
python -m pip install --upgrade pip
python -m pip install -U pip setuptools
python -m pip install -r requirements.txt
python -m pip install git+https://github.com/sfahad1414/question_generation.git
python -m spacy download en_core_web_md
python -m spacy link en_core_web_md en
python -m nltk.downloader wordnet
python -m nltk.downloader averaged_perceptron_tagger
python -m nltk.downloader punkt