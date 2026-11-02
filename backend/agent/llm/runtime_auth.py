from __future__ import annotations


def runtime_headers(provider: str | None, api_key: str | None) -> dict[str, str]:
    """Use only this runtime's credentials; local OpenAI services may be keyless."""
    key = str(api_key or "").strip()
    provider_name = str(provider or "").strip().lower()
    if not key and provider_name != "local_openai":
        raise RuntimeError(f"api key is not configured for provider '{provider_name}' in model config page")
    headers: dict[str, str] = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers
