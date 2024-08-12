#!/bin/bash
python -m pip install -r requirements/dev.txt
python -c "import spacy; spacy.cli.download('en_core_web_md')"
python -m spacy link en_core_web_md en
python -c "import nltk;nltk.download('averaged_perceptron_tagger_eng')"
python -c "import nltk;nltk.download('averaged_perceptron_tagger')"
python -c "import nltk;nltk.download('punkt')"
python -c "import nltk;nltk.download('stopwords')"
python -c "import nltk;nltk.download('omw-1.4')"
python -c "import nltk;nltk.download('wordnet')"