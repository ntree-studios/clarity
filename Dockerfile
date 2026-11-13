# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY pyproject.toml ./
COPY src ./src
ENV NLTK_DATA=/opt/nltk_data
RUN pip install --no-cache-dir . \
 && python -m spacy download en_core_web_sm \
 && python -m nltk.downloader -d /opt/nltk_data \
      wordnet brown universal_tagset punkt punkt_tab \
      averaged_perceptron_tagger averaged_perceptron_tagger_eng \
 && python -m clarity.punct_model

FROM builder AS dev
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e '.[dev]' \
 && python -m clarity.punct_model

FROM python:3.12-slim AS runtime
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/nltk_data /opt/nltk_data
ENV PATH=/opt/venv/bin:$PATH \
    CLARITY_HOME=/config \
    NLTK_DATA=/opt/nltk_data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN clarity init
LABEL org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="N-Tree Studios"
ENTRYPOINT ["clarity"]
