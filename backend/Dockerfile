FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_ENDPOINT=https://hf-mirror.com

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        curl \
        fonts-wqy-microhei \
        g++ && \
    rm -rf /var/lib/apt/lists/* && \
    python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt && \
    python - <<'PY'
from macro_correct.predict_csc_token_zh import download_model_from_huggface_with_url as dl_token
from macro_correct.predict_csc_punct_zh import download_model_from_huggface_with_url as dl_punct

endpoint = "https://hf-mirror.com"
dl_token(repo_id="Macropodus/macbert4mdcspell_v3", hf_endpoint=endpoint)
dl_punct(repo_id="Macropodus/bert4sl_punct_zh_public", hf_endpoint=endpoint)
print("macro_correct models downloaded")
PY

COPY backend/ ./

EXPOSE 8000
