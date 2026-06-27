from app.schemas.governance import ModelConfigUpdate


def test_model_config_update_allows_provider_correction():
    payload = ModelConfigUpdate(provider=" deepseek ")

    assert payload.provider == "deepseek"
