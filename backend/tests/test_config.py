from pathlib import Path

from app.api.v1 import langfuse_proxy
from app.core.config import Settings


def test_langfuse_blank_values_normalize_to_none():
    settings = Settings(
        langfuse_enabled=False,
        langfuse_host="",
        langfuse_public_host="null",
        langfuse_public_key="undefined",
        langfuse_secret_key="",
        langfuse_project_id="none",
    )

    assert settings.langfuse_host is None
    assert settings.langfuse_public_host is None
    assert settings.langfuse_public_key is None
    assert settings.langfuse_secret_key is None
    assert settings.langfuse_project_id is None


def test_langfuse_redirect_uses_configured_host(monkeypatch):
    monkeypatch.setattr(langfuse_proxy.settings, "langfuse_host", "http://127.0.0.1:3000/")

    assert langfuse_proxy._langfuse_auth_base_url() == "http://127.0.0.1:3000"


def test_jwt_pem_escape_sequences_normalize_to_real_newlines():
    settings = Settings(
        jwt_private_key="-----BEGIN PRIVATE KEY-----\\nline1\\nline2\\n-----END PRIVATE KEY-----",
        jwt_public_key="-----BEGIN PUBLIC KEY-----\\nlineA\\nlineB\\n-----END PUBLIC KEY-----",
    )

    assert "\n" not in settings.jwt_private_key.splitlines()[0]
    assert settings.jwt_private_key.count("\n") == 3
    assert settings.jwt_public_key.count("\n") == 3


def test_jwt_pem_file_paths_load_file_contents(tmp_path: Path):
    private_key = tmp_path / "jwt_private.pem"
    public_key = tmp_path / "jwt_public.pem"
    private_key.write_text("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n", encoding="utf-8")
    public_key.write_text("-----BEGIN PUBLIC KEY-----\nxyz\n-----END PUBLIC KEY-----\n", encoding="utf-8")

    settings = Settings(
        jwt_private_key=str(private_key),
        jwt_public_key=str(public_key),
    )

    assert settings.jwt_private_key == "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"
    assert settings.jwt_public_key == "-----BEGIN PUBLIC KEY-----\nxyz\n-----END PUBLIC KEY-----"
