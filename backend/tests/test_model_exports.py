import app.models as models


def test_tool_registry_is_not_exported_from_app_models():
    assert "ToolRegistry" not in models.__all__
    assert not hasattr(models, "ToolRegistry")
