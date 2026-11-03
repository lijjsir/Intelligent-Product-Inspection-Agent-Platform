import importlib.util
import json
from pathlib import Path

import pytest

import qdl_http
from predict import _direct_image_rows, _prompt

spec = importlib.util.spec_from_file_location(
    "detect_defects_entry", Path(__file__).resolve().parents[2] / "scripts/detect_defects.py"
)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def test_project_entry_defaults_to_json_and_separate_output_per_run():
    first = entry.prepare_arguments(["--image", "image.png"])
    second = entry.prepare_arguments(["--image", "image.png"])
    assert first[first.index("--prompt-mode") + 1] == "open-vocab"
    assert first[first.index("--output") + 1] != second[second.index("--output") + 1]
    assert Path(first[first.index("--output") + 1]).parent == entry.QDL_DIR / "results"


def test_explicit_options_and_resume_are_preserved():
    args = ["--output=custom.jsonl", "--resume", "--prompt-mode=evidence-first"]
    assert entry.prepare_arguments(args) == args
    with pytest.raises(ValueError, match="requires --output"):
        entry.prepare_arguments(["--resume"])


def test_config_environment_has_priority_over_machine_local_file(tmp_path, monkeypatch):
    monkeypatch.setattr(qdl_http, "__file__", str(tmp_path / "qdl_http.py"))
    (tmp_path / "config.local.json").write_text(json.dumps({"base_url": "http://local.test/v1", "model": "local"}))
    monkeypatch.delenv("QDL_BASE_URL", raising=False)
    monkeypatch.delenv("QDL_MODEL", raising=False)
    assert qdl_http.runtime_defaults() == ("http://local.test/v1", "local")
    monkeypatch.setenv("QDL_BASE_URL", "http://override.test/v1")
    monkeypatch.setenv("QDL_MODEL", "override")
    assert qdl_http.runtime_defaults() == ("http://override.test/v1", "override")


def test_defect_folder_names_are_not_sent_as_product_labels():
    rows = _direct_image_rows(["dataset/scratch/001.png", "dataset/good/001.png"], None, "inspect", "test")
    assert rows[0]["id"] != rows[1]["id"]
    assert all(row["category"] == "industrial product" for row in rows)
    assert "scratch" not in _prompt(rows[0], "open-vocab")
    explicit = _direct_image_rows(["dataset/scratch/001.png"], None, "inspect", "test", "bottle")
    assert "bottle" in _prompt(explicit[0], "open-vocab")
