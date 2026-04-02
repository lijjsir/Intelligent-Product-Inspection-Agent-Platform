FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt

RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY backend/ ./

EXPOSE 8000

