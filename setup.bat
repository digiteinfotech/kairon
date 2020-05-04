python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m spacy download en_core_web_md
python -m spacy link en_core_web_md en
python -m gensim.downloader --download word2vec-google-news-300