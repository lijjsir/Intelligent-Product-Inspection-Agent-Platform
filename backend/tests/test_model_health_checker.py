from agent.llm.health_checker import ModelHealthChecker


def test_missing_model_key_message_includes_available_candidates():
    message = ModelHealthChecker._missing_model_key_message(
        "target-model",
        {"model-b", "model-a", "model-c", "model-d", "model-e", "model-f"},
    )

    assert message is not None
    assert "missing model_key: target-model" in message
    assert "available: [model-a, model-b, model-c, model-d, model-e]" in message


def test_direct_probe_success_message_includes_available_candidates():
    message = ModelHealthChecker._direct_probe_success_message(
        "ep-test",
        {"deepseek-r1", "deepseek-r1-250120"},
        probe_path="/chat/completions",
    )

    assert message is not None
    assert "/chat/completions accepted model_key: ep-test" in message
    assert "available: [deepseek-r1, deepseek-r1-250120]" in message
