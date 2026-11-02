import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("ollama_user", Path(__file__).with_name("install-ollama-user.py"))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_service_keeps_model_files_in_user_home_and_uses_both_gpus():
    unit = installer.service_text(Path("/home/admin2"), "172.17.0.1:11434", 16384)
    assert "OLLAMA_MODELS=/home/admin2/ai_models/ollama" in unit
    assert "CUDA_VISIBLE_DEVICES=0,1" in unit
    assert "OLLAMA_SCHED_SPREAD=true" in unit
    assert "OLLAMA_NUM_PARALLEL=1" in unit
    assert "OLLAMA_NO_CLOUD=1" in unit
    assert "OLLAMA_CONTEXT_LENGTH=16384" in unit
    assert "sudo" not in unit


def test_service_does_not_accidentally_bind_public_interface():
    with pytest.raises(ValueError):
        installer.service_text(Path("/home/admin2"), "0.0.0.0:11434", 16384)
