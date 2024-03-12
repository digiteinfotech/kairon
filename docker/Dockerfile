FROM amazonlinux:latest

ENV KAIRON_HOME=/app PYTHON_VERSION=3.10.13

WORKDIR ${KAIRON_HOME}

RUN yum update -y
RUN dnf -y update kernel expat gnutls openssl --releasever 2023.3.20240219

RUN yum update -y && yum -y install wget make gcc zlib-devel tar xz gzip openssl openssl-devel bzip2-devel sqlite-devel libffi-devel openblas-devel ca-certificates
RUN wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz && \
    tar -xf Python-${PYTHON_VERSION}.tgz && \
    rm ./Python-${PYTHON_VERSION}.tgz && \
    cd Python-${PYTHON_VERSION}/ && \
    ./configure --enable-optimizations && \
    make altinstall && \
    rm -rf Python-${PYTHON_VERSION} && \
    update-alternatives --install /usr/bin/python python /usr/bin/python2 50 && \
    update-alternatives --install /usr/bin/python python /usr/local/bin/python3.10 60 && \
    python -m pip install --upgrade pip && \
    mkdir data_generator training_data testing_data models /home/cache .rasa


COPY requirements requirements
RUN python -m pip --no-cache-dir install -r ./requirements/prod.txt && \
    python -m spacy download en_core_web_md && \
    python -m nltk.downloader averaged_perceptron_tagger && \
    python -m nltk.downloader punkt && \
    python -m nltk.downloader stopwords && \
    python -m nltk.downloader omw-1.4 && \
    python -m nltk.downloader wordnet && \
    rm -rf requirements

RUN opentelemetry-bootstrap -a install
RUN python -m pip install pyston_lite_autoload
COPY . .

ENV HF_HOME="/home/cache" SENTENCE_TRANSFORMERS_HOME="/home/cache"

