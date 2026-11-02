from pathlib import Path

import pytest
import yaml

from agent.llm.base_url_resolver import resolve_runtime_base_url
from agent.llm.runtime_auth import runtime_headers


@pytest.mark.parametrize("url,expected", [
    ("http://localhost:11434/v1", "http://host.docker.internal:11434/v1"),
    ("http://127.0.0.1:8001/v1", "http://host.docker.internal:8001/v1"),
    ("http://localhost:9000/custom/v1", "http://host.docker.internal:9000/custom/v1"),
    ("http://10.16.125.125:8001/v1", "http://10.16.125.125:8001/v1"),
    ("http://model-service:11434", "http://model-service:11434/v1"),
])
def test_local_model_endpoint_preserves_selected_service(monkeypatch, url, expected):
    monkeypatch.setattr("agent.llm.base_url_resolver.os.path.exists", lambda path: path == "/.dockerenv")
    monkeypatch.setattr("agent.llm.base_url_resolver.settings.local_openai_base_url", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr("agent.llm.base_url_resolver.settings.local_openai_docker_base_url", "http://host.docker.internal:11434/v1")
    assert resolve_runtime_base_url("local_openai", url) == expected


def test_configured_default_container_endpoint_can_override_port(monkeypatch):
    monkeypatch.setattr("agent.llm.base_url_resolver.os.path.exists", lambda path: path == "/.dockerenv")
    monkeypatch.setattr("agent.llm.base_url_resolver.settings.local_openai_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr("agent.llm.base_url_resolver.settings.local_openai_docker_base_url", "http://inference:8001/v1")
    assert resolve_runtime_base_url("local_openai", "http://127.0.0.1:11434/v1") == "http://inference:8001/v1"


def test_cloud_credentials_are_still_required():
    with pytest.raises(RuntimeError, match="api key is not configured"):
        runtime_headers("deepseek", None)
    assert "Authorization" not in runtime_headers(" LOCAL_OPENAI ", "")
    assert runtime_headers("local_openai", " local-key ")["Authorization"] == "Bearer local-key"


def test_lab_app_services_all_resolve_host_gateway():
    project = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((project / "compose.lab.yml").read_text(encoding="utf-8"))
    for service in ("backend", "celery-worker", "celery-beat"):
        assert "host.docker.internal:host-gateway" in compose["services"][service]["extra_hosts"]
