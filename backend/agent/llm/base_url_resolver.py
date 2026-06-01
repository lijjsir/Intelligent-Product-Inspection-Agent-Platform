from __future__ import annotations

import os
from urllib.parse import urlsplit

from app.core.config import settings


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def resolve_runtime_base_url(provider: str | None, base_url: str | None) -> str:
    provider_name = str(provider or "").strip().lower()
    candidate = str(base_url or "").strip().rstrip("/")

    if provider_name != "local_openai":
        return candidate

    if not candidate:
        candidate = default_local_openai_base_url()

    return _maybe_remap_local_openai_loopback(candidate)


def resolve_runtime_service_url(base_url: str | None, *, docker_base_url: str | None = None) -> str:
    candidate = str(base_url or "").strip().rstrip("/")
    docker_candidate = str(docker_base_url or "").strip().rstrip("/")

    if not candidate:
        if os.path.exists("/.dockerenv") and docker_candidate:
            return docker_candidate
        return candidate

    if not os.path.exists("/.dockerenv"):
        return candidate

    host = (urlsplit(candidate).hostname or "").strip().lower()
    if host not in _LOOPBACK_HOSTS:
        return candidate

    return docker_candidate or candidate


def default_local_openai_base_url() -> str:
    running_in_container = os.path.exists("/.dockerenv")
    base_url = settings.local_openai_docker_base_url if running_in_container else settings.local_openai_base_url
    return str(base_url or "").strip().rstrip("/")


def _maybe_remap_local_openai_loopback(base_url: str) -> str:
    if not os.path.exists("/.dockerenv"):
        return base_url

    host = (urlsplit(base_url).hostname or "").strip().lower()
    if host not in _LOOPBACK_HOSTS:
        return base_url

    docker_base_url = str(settings.local_openai_docker_base_url or "").strip().rstrip("/")
    return docker_base_url or base_url
