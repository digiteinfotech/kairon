FROM amazonlinux:latest

ENV KAIRON_HOME=/app PYTHON_VERSION=3.10.16 TEMPLATE_DIR_DEFAULT=./template/use-cases/Hi-Hello-GPT RASA_TELEMETRY_ENABLED=false
ENV PYENV_ROOT=/root/.pyenv
ENV PATH=$PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH

WORKDIR ${KAIRON_HOME}


RUN yum update -y
RUN yum install -y wget make gcc zlib-devel tar xz gzip openssl openssl-devel bzip2-devel sqlite-devel libffi-devel openblas-devel ca-certificates git ncurses-devel readline-devel xz-devel tk-devel bzip2 patch sqlite
RUN yum install -y pango pango-devel

RUN curl https://pyenv.run | bash
RUN echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc && \
    echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc && \
    echo 'eval "$(pyenv init -)"' >> ~/.zshrc

RUN source ~/.zshrc && \
    pyenv install ${PYTHON_VERSION} && \
    pyenv global ${PYTHON_VERSION} &&  \
    pyenv rehash &&  \
    python -m pip install --upgrade pip && \
    mkdir data_generator training_data testing_data models /home/cache .rasa


COPY requirements requirements
RUN python -m pip --no-cache-dir install -r ./requirements/prod.txt && \
    python -m spacy download en_core_web_md && \
    python -m nltk.downloader averaged_perceptron_tagger && \
    python -m nltk.downloader averaged_perceptron_tagger_eng && \
    python -m nltk.downloader punkt && \
    python -m nltk.downloader stopwords && \
    python -m nltk.downloader omw-1.4 && \
    python -m nltk.downloader wordnet && \
    rm -rf requirements

RUN python -m pip install pyston_lite_autoload
COPY . .

RUN rm -rf ${TEMPLATE_DIR_DEFAULT}/models/* && \
    python -m rasa train --data ${TEMPLATE_DIR_DEFAULT}/data --config ${TEMPLATE_DIR_DEFAULT}/config.yml --domain ${TEMPLATE_DIR_DEFAULT}/domain.yml --out ${TEMPLATE_DIR_DEFAULT}/models

RUN cp kairon/shared/rule_policy.py /root/.pyenv/versions/${PYTHON_VERSION}/lib/python3.10/site-packages/rasa/core/policies/rule_policy.py
RUN cp kairon/shared/schemas/domain.yml /root/.pyenv/versions/${PYTHON_VERSION}/lib/python3.10/site-packages/rasa/shared/utils/schemas/domain.yml

ENV HF_HOME="/home/cache" SENTENCE_TRANSFORMERS_HOME="/home/cache"

