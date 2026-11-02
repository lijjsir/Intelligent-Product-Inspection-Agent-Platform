from agent.llm.runtime_options import apply_runtime_options


def test_local_options_control_thinking_and_output_budget(monkeypatch):
    monkeypatch.setattr("agent.llm.runtime_options.settings.local_model_reasoning_effort", "none")
    monkeypatch.setattr("agent.llm.runtime_options.settings.local_model_max_tokens", 2048)
    source = {"model": "qwen3.5:9b-q8_0", "messages": []}
    assert apply_runtime_options(source, "local_openai") == {
        **source, "reasoning_effort": "none", "max_tokens": 2048,
    }
    assert source == {"model": "qwen3.5:9b-q8_0", "messages": []}


def test_local_options_preserve_explicit_experimental_parameters(monkeypatch):
    monkeypatch.setattr("agent.llm.runtime_options.settings.local_model_reasoning_effort", "none")
    source = {"messages": [], "max_tokens": 8192, "reasoning_effort": "high"}
    assert apply_runtime_options(source, "local_openai") == source


def test_local_options_do_not_change_cloud_or_embedding_payloads(monkeypatch):
    monkeypatch.setattr("agent.llm.runtime_options.settings.local_model_reasoning_effort", "none")
    assert apply_runtime_options({"messages": []}, "deepseek") == {"messages": []}
    assert apply_runtime_options({"input": ["hello"]}, "local_openai") == {"input": ["hello"]}
