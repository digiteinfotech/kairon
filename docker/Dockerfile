FROM amazonlinux:latest

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

ENV KAIRON_HOME=/app \
    TEMPLATE_DIR_DEFAULT=./template/use-cases/Hi-Hello-GPT \
    RASA_TELEMETRY_ENABLED=false \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=3.10 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME="/home/cache" \
    SENTENCE_TRANSFORMERS_HOME="/home/cache"

WORKDIR ${KAIRON_HOME}

RUN yum update -y && \
    yum install -y \
      ca-certificates \
      git \
      gcc \
      gcc-c++ \
      make \
      tar \
      gzip \
      bzip2 \
      xz \
      openssl \
      openssl-devel \
      libffi-devel \
      openblas-devel \
      libgomp && \
    yum clean all && \
    rm -rf /var/cache/yum

RUN mkdir -p data_generator training_data testing_data models /home/cache .rasa

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project && \
    uv pip install pyston_lite_autoload

COPY . .

RUN rm -rf ${TEMPLATE_DIR_DEFAULT}/models/* && \
    python -m rasa train --data ${TEMPLATE_DIR_DEFAULT}/data --config ${TEMPLATE_DIR_DEFAULT}/config.yml --domain ${TEMPLATE_DIR_DEFAULT}/domain.yml --out ${TEMPLATE_DIR_DEFAULT}/models

RUN python -c "import pathlib, shutil, rasa; root = pathlib.Path(rasa.__file__).resolve().parent; shutil.copy('kairon/shared/rule_policy.py', root / 'core/policies/rule_policy.py'); shutil.copy('kairon/shared/schemas/domain.yml', root / 'shared/utils/schemas/domain.yml')"
