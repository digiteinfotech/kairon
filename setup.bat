python -m pip install --upgrade pip
python -m pip install torch==1.5.0+cpu torchvision==0.6.0+cpu -f https://download.pytorch.org/whl/torch_stable.html
python -m pip install -r requirements.txt
python -m spacy download en_core_web_md
python -m spacy link en_core_web_md en
python -m nltk.downloader wordnet
python -m nltk.downloader averaged_perceptron_tagger