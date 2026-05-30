from __future__ import annotations

import json

from scripts import download_paper_review_assets


def _write_asset_set(base_dir, repo_key: str) -> None:
    if repo_key == "token":
        target = base_dir / "macro_correct" / "token"
        files = download_paper_review_assets.TOKEN_FILES
    else:
        target = base_dir / "macro_correct" / "punct"
        files = download_paper_review_assets.PUNCT_FILES
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        (target / name).write_bytes(b"asset")


def test_download_assets_skips_huggingface_when_manifest_and_files_are_ready(monkeypatch, tmp_path):
    _write_asset_set(tmp_path, "token")
    _write_asset_set(tmp_path, "punct")
    download_paper_review_assets._write_manifest(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(
        download_paper_review_assets,
        "snapshot_download",
        lambda **kwargs: calls.append(str(kwargs["repo_id"])),
    )

    assert download_paper_review_assets.prepare_assets(tmp_path) is False
    assert calls == []


def test_download_assets_repairs_missing_manifest_without_redownloading(monkeypatch, tmp_path):
    _write_asset_set(tmp_path, "token")
    _write_asset_set(tmp_path, "punct")
    calls: list[str] = []

    monkeypatch.setattr(
        download_paper_review_assets,
        "snapshot_download",
        lambda **kwargs: calls.append(str(kwargs["repo_id"])),
    )

    assert download_paper_review_assets.prepare_assets(tmp_path) is True
    assert calls == []
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["asset_version"] == "paper-check-assets-v1"


def test_download_assets_downloads_only_missing_repo(monkeypatch, tmp_path):
    _write_asset_set(tmp_path, "token")
    calls: list[str] = []

    def fake_snapshot_download(**kwargs):
        calls.append(str(kwargs["repo_id"]))
        target = kwargs["local_dir"]
        for name in download_paper_review_assets.PUNCT_FILES:
            (download_paper_review_assets.Path(target) / name).write_bytes(b"asset")

    monkeypatch.setattr(download_paper_review_assets, "snapshot_download", fake_snapshot_download)

    assert download_paper_review_assets.prepare_assets(tmp_path) is True
    assert calls == [download_paper_review_assets.PUNCT_REPO]
