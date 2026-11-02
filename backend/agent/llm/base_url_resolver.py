from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from app.core.config import settings


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def resolve_runtime_base_url(provider: str | None, base_url: str | None) -> str:
    provider_name = str(provider or "").strip().lower()
    candidate = str(base_url or "").strip().rstrip("/")

    if provider_name != "local_openai":
        return candidate

    if not candidate:
        candidate = default_local_openai_base_url()

    candidate = _maybe_remap_local_openai_loopback(candidate)
    parsed = urlsplit(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.path.strip("/"):
        candidate = urlunsplit(parsed._replace(path="/v1"))
    return candidate


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
    if not docker_base_url:
        return base_url
    original = urlsplit(base_url)
    configured_local = urlsplit(str(settings.local_openai_base_url or ""))
    # The configured default may intentionally use a different container port/path.
    if original.port == configured_local.port and original.path.rstrip("/") == configured_local.path.rstrip("/"):
        return docker_base_url
    docker = urlsplit(docker_base_url)
    docker_host = docker.hostname
    if not docker_host:
        return base_url
    if ":" in docker_host:
        docker_host = f"[{docker_host}]"
    netloc = f"{docker_host}:{original.port}" if original.port else docker_host
    # Explicit alternative servers (e.g. vLLM on 8001) keep their own port/path.
    return urlunsplit(original._replace(netloc=netloc))
