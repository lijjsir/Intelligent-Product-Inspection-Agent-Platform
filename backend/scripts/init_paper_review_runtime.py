from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


HF_ENDPOINT = os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
MODEL_SPECS = (
    (
        "Macropodus/macbert4mdcspell_v3",
        Path("output/text_correction/macbert4mdcspell_v3"),
        "csc.config",
        (
            "config.json",
            "csc.config",
            "generation_config.json",
            "pytorch_model.bin",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
        ),
    ),
    (
        "Macropodus/bert4sl_punct_zh_public",
        Path("output/sequence_labeling/bert4sl_punct_zh_public"),
        "sl.config",
        (
            "config.json",
            "idx2pun.json",
            "pytorch_model.bin",
            "sl.config",
            "special_tokens_map.json",
            "tokenizer_config.json",
            "vocab.txt",
        ),
    ),
)
CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT = httpx.Timeout(180.0, connect=20.0)


def _require_import(name: str) -> object:
    module = __import__(name)
    print(f"[ok] import {name}: {getattr(module, '__file__', 'built-in')}")
    return module


def _download_repo_file(repo_id: str, filename: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"{HF_ENDPOINT.rstrip('/')}/{quote(repo_id, safe='/')}/resolve/main/{quote(filename)}"
    partial_path = target.with_suffix(target.suffix + ".part")
    existing_size = partial_path.stat().st_size if partial_path.exists() else 0
    headers = {}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"

    print(f"[run] download {repo_id}/{filename} -> {target}")
    with httpx.stream(
        "GET",
        url,
        headers=headers,
        timeout=DOWNLOAD_TIMEOUT,
        follow_redirects=True,
    ) as response:
        if response.status_code == 416 and partial_path.exists():
            partial_path.rename(target)
            print(f"[ok] download already complete: {target}")
            return
        response.raise_for_status()
        append_mode = "ab" if response.status_code == 206 and existing_size > 0 else "wb"
        if append_mode == "wb" and partial_path.exists():
            partial_path.unlink()
        with partial_path.open(append_mode) as f:
            for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
    partial_path.rename(target)
    print(f"[ok] downloaded {filename}")


def _ensure_macro_correct_models() -> None:
    macro_correct = _require_import("macro_correct")
    package_root = Path(macro_correct.__file__).resolve().parent

    for repo_id, rel_dir, config_name, allow_patterns in MODEL_SPECS:
        model_dir = package_root / rel_dir
        config_path = model_dir / config_name
        model_path = model_dir / "pytorch_model.bin"
        if config_path.exists() and model_path.exists():
            print(f"[ok] macro_correct model ready: {model_dir}")
            continue

        model_dir.mkdir(parents=True, exist_ok=True)
        for filename in allow_patterns:
            target = model_dir / filename
            if target.exists() and target.stat().st_size > 0:
                print(f"[ok] file ready: {target}")
                continue
            _download_repo_file(repo_id, filename, target)
        if not config_path.exists() or not model_path.exists():
            raise RuntimeError(f"model download incomplete: {model_dir}")
        print(f"[ok] downloaded {repo_id}")


def _ensure_pycorrector_language_model() -> None:
    from agent.tools.paper_review_pycorrector import _configure_pycorrector_env
    from pycorrector.detector import Detector

    kwargs = _configure_pycorrector_env()
    model_path = Path(str(kwargs["language_model_path"]))
    if model_path.exists() and model_path.stat().st_size > 0:
        print(f"[ok] pycorrector model ready: {model_path}")
        return

    model_path.parent.mkdir(parents=True, exist_ok=True)
    filename = model_path.name
    url = Detector.pretrained_language_models.get(filename)
    if not url:
        raise RuntimeError(f"unsupported pycorrector language model: {filename}")
    print(f"[run] download pycorrector model {filename} -> {model_path}")
    _download_http_file(url, model_path)
    print(f"[ok] downloaded pycorrector model: {model_path}")


def _download_http_file(url: str, target: Path) -> None:
    partial_path = target.with_suffix(target.suffix + ".part")
    existing_size = partial_path.stat().st_size if partial_path.exists() else 0
    headers = {}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"

    with httpx.stream(
        "GET",
        url,
        headers=headers,
        timeout=DOWNLOAD_TIMEOUT,
        follow_redirects=True,
    ) as response:
        if response.status_code == 416 and partial_path.exists():
            partial_path.rename(target)
            return
        response.raise_for_status()
        append_mode = "ab" if response.status_code == 206 and existing_size > 0 else "wb"
        if append_mode == "wb" and partial_path.exists():
            partial_path.unlink()
        with partial_path.open(append_mode) as f:
            for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
    partial_path.rename(target)


def _warm_vale() -> None:
    vale_bin = shutil.which("vale") or str(Path(sys.executable).with_name("vale"))
    print(f"[run] warm vale: {vale_bin}")
    completed = subprocess.run(
        [vale_bin, "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    version_text = (completed.stdout or completed.stderr).strip()
    print(f"[ok] vale: {version_text}")


def main() -> int:
    _require_import("kenlm")
    _ensure_macro_correct_models()
    _ensure_pycorrector_language_model()
    from agent.tools.paper_review_pycorrector import run_pycorrector

    print("[run] warm pycorrector")
    run_pycorrector("这是一个测试。")
    print("[ok] pycorrector warmed")
    _warm_vale()

    from app.services.paper_review_runtime_service import PaperReviewRuntimeService

    status = PaperReviewRuntimeService.diagnose_sync()
    print(status)
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
