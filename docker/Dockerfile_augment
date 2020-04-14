FROM python:3.7.7

SHELL ["/bin/bash", "-c"]

ENV RASA_NLU_DOCKER="YES" \
    RASA_NLU_HOME=/app \
    RASA_NLU_PYTHON_PACKAGES=/usr/local/lib/python3.6/dist-packages

WORKDIR ${RASA_NLU_HOME}

RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install pyyaml
RUN python3 -m pip install rasa==1.9.5
RUN python3 -m pip install gensim
RUN python3 -m pip install sentence_transformers
RUN python3 -m pip install autocorrect
RUN python3 -m pip install Quart
RUN python3 -m pip install Quart-CORS
RUN python3 -m pip install spacy
RUN python3 -m spacy download en_core_web_sm
RUN python3 -m nltk.downloader punkt
RUN python3 -m nltk.downloader wordnet
RUN python3 -m nltk.downloader averaged_perceptron_tagger
RUN python3 -m pip install tensorflow_text
RUN python3 -m pip install cython
RUN python3 -m pip install pandas
RUN mkdir ssl

COPY . ${RASA_NLU_HOME}

RUN python3 setup.py build_ext

EXPOSE 8000

CMD ["hypercorn","-w", "2", "trainer:app","-b","0.0.0.0:8000"]
