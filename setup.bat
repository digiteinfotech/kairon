python -m pip install -r requirements/dev.txt
python -m spacy download en_core_web_md
python -m spacy link en_core_web_md en
python -m nltk.downloader averaged_perceptron_tagger
python -m nltk.downloader punkt
python -m nltk.downloader stopwords
python -m nltk.downloader omw-1.4
python -m nltk.downloader wordnet