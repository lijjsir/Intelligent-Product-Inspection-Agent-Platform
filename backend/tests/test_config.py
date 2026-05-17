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
