FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_ENDPOINT=https://hf-mirror.com

ARG PIAP_PRELOAD_MACRO_CORRECT_MODELS=false
ARG PIAP_INSTALL_ML_DEPS=false

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements ./requirements

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        curl \
        fonts-wqy-microhei \
        g++ \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        tesseract-ocr-eng && \
    rm -rf /var/lib/apt/lists/* && \
    python -m pip install --upgrade pip && \
    python -m pip install -r requirements/base.txt && \
    if [ "$PIAP_INSTALL_ML_DEPS" = "true" ]; then \
        python -m pip install -r requirements/ml.txt; \
    else \
        echo "ML paper-review dependencies skipped; set PIAP_INSTALL_ML_DEPS=true to include them"; \
    fi

RUN if [ "$PIAP_PRELOAD_MACRO_CORRECT_MODELS" = "true" ]; then \
        if [ "$PIAP_INSTALL_ML_DEPS" != "true" ]; then \
            echo "PIAP_PRELOAD_MACRO_CORRECT_MODELS=true requires PIAP_INSTALL_ML_DEPS=true" >&2; \
            exit 1; \
        fi; \
        python -c "from macro_correct.predict_csc_token_zh import download_model_from_huggface_with_url as dl_token; from macro_correct.predict_csc_punct_zh import download_model_from_huggface_with_url as dl_punct; endpoint='https://hf-mirror.com'; dl_token(repo_id='Macropodus/macbert4mdcspell_v3', hf_endpoint=endpoint); dl_punct(repo_id='Macropodus/bert4sl_punct_zh_public', hf_endpoint=endpoint); print('macro_correct models downloaded')"; \
    else \
        echo "macro_correct model preload skipped; set PIAP_PRELOAD_MACRO_CORRECT_MODELS=true to bake them into the image"; \
    fi

ENV PIAP_PAPER_REVIEW_ENABLED=false \
    PIAP_PAPER_CHECK_PYCORRECTOR_ENABLED=false \
    PIAP_PAPER_CHECK_MACRO_CORRECT_ENABLED=false

COPY backend/ ./

EXPOSE 8000
