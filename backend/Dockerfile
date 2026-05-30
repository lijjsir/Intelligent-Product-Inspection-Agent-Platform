FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIAP_PAPER_CHECK_PYCORRECTOR_ENTRYPOINT=macbert_local \
    PIAP_PAPER_CHECK_PYCORRECTOR_MODEL_DIR=/opt/piap-paper-assets/macro_correct/token \
    PIAP_PAPER_CHECK_MACRO_CORRECT_TOKEN_CONFIG=/opt/piap-paper-assets/macro_correct/token/csc.config \
    PIAP_PAPER_CHECK_MACRO_CORRECT_PUNCT_CONFIG=/opt/piap-paper-assets/macro_correct/punct/sl.config \
    PIAP_PAPER_CHECK_VALE_BIN=/usr/local/bin/vale

WORKDIR /app/backend

ARG VALE_VERSION=3.13.0

COPY backend/requirements.txt ./requirements.txt

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl fonts-wqy-microhei wget && \
    curl -fsSL "https://github.com/vale-cli/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz" -o /tmp/vale.tar.gz && \
    tar -xzf /tmp/vale.tar.gz -C /tmp vale && \
    install -m 0755 /tmp/vale /usr/local/bin/vale && \
    rm -f /tmp/vale /tmp/vale.tar.gz && \
    rm -rf /var/lib/apt/lists/* && \
    python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY backend/ ./

# Patch macro_correct for transformers 5.x AdamW compatibility
RUN PYTHONPATH=. python scripts/patch_macro_correct_transformers.py

EXPOSE 8000
