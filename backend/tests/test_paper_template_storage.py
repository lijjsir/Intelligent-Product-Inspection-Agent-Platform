from __future__ import annotations

from pathlib import Path

from agent.tools.paper_template_storage import (
    get_cqupt_graduate_template_asset_paths,
    seed_builtin_paper_templates,
    seed_cqupt_graduate_templates,
)


def test_seed_cqupt_graduate_templates_uploads_both_docx_files(tmp_path: Path):
    commented = tmp_path / "commented.docx"
    guide = tmp_path / "guide.docx"
    commented.write_bytes(b"commented-template")
    guide.write_bytes(b"writing-guide")
    stored: dict[tuple[str, str], tuple[bytes, str | None]] = {}

    class FakeStorage:
        def put_bytes(self, *, bucket, object_key, data, content_type=None):
            stored[(bucket, object_key)] = (data, content_type)
            return {
                "bucket": bucket,
                "object_key": object_key,
                "content_type": content_type,
                "size_bytes": len(data),
                "url": f"/api/v1/chat/files/{bucket}/{object_key}",
            }

    result = seed_cqupt_graduate_templates(
        storage=FakeStorage(),
        commented_template_path=commented,
        writing_guide_path=guide,
    )

    assert result["template_id"] == "cqupt_graduate_thesis_2022"
    assert len(result["files"]) == 2
    assert stored[
        ("paper-templates", "cqupt/graduate-thesis/2022/word-commented-template.docx")
    ] == (
        b"commented-template",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert stored[
        ("paper-templates", "cqupt/graduate-thesis/2022/writing-guide.docx")
    ] == (
        b"writing-guide",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def test_cqupt_template_seed_assets_are_committed():
    paths = get_cqupt_graduate_template_asset_paths()

    assert paths["word_commented_template"].is_file()
    assert paths["writing_guide"].is_file()
    assert paths["word_commented_template"].stat().st_size > 0
    assert paths["writing_guide"].stat().st_size > 0


def test_seed_builtin_paper_templates_uses_committed_assets():
    stored: dict[tuple[str, str], tuple[int, str | None]] = {}

    class FakeStorage:
        def put_bytes(self, *, bucket, object_key, data, content_type=None):
            stored[(bucket, object_key)] = (len(data), content_type)
            return {
                "bucket": bucket,
                "object_key": object_key,
                "content_type": content_type,
                "size_bytes": len(data),
                "url": f"/api/v1/chat/files/{bucket}/{object_key}",
            }

    result = seed_builtin_paper_templates(storage=FakeStorage())

    assert result["template_id"] == "cqupt_graduate_thesis_2022"
    assert stored[("paper-templates", "cqupt/graduate-thesis/2022/word-commented-template.docx")][0] > 0
    assert stored[("paper-templates", "cqupt/graduate-thesis/2022/writing-guide.docx")][0] > 0


def test_seed_cqupt_graduate_templates_skips_existing_objects(tmp_path: Path):
    commented = tmp_path / "commented.docx"
    guide = tmp_path / "guide.docx"
    commented.write_bytes(b"commented-template")
    guide.write_bytes(b"writing-guide")
    put_calls: list[tuple[str, str]] = []

    class FakeStorage:
        def get_bytes(self, *, bucket, object_key):
            return b"already-exists", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        def put_bytes(self, *, bucket, object_key, data, content_type=None):
            put_calls.append((bucket, object_key))
            return {
                "bucket": bucket,
                "object_key": object_key,
                "content_type": content_type,
                "size_bytes": len(data),
                "url": f"/api/v1/chat/files/{bucket}/{object_key}",
            }

    result = seed_cqupt_graduate_templates(
        storage=FakeStorage(),
        commented_template_path=commented,
        writing_guide_path=guide,
    )

    assert put_calls == []
    assert [item["status"] for item in result["files"]] == ["exists", "exists"]


def test_seed_cqupt_graduate_templates_prefers_object_exists(tmp_path: Path):
    commented = tmp_path / "commented.docx"
    guide = tmp_path / "guide.docx"
    commented.write_bytes(b"commented-template")
    guide.write_bytes(b"writing-guide")
    exists_calls: list[tuple[str, str]] = []

    class FakeStorage:
        def object_exists(self, *, bucket, object_key):
            exists_calls.append((bucket, object_key))
            return True

        def get_bytes(self, *, bucket, object_key):
            raise AssertionError("get_bytes should not be used when object_exists is available")

        def put_bytes(self, *, bucket, object_key, data, content_type=None):
            raise AssertionError("existing objects should not be uploaded")

    result = seed_cqupt_graduate_templates(
        storage=FakeStorage(),
        commented_template_path=commented,
        writing_guide_path=guide,
    )

    assert len(exists_calls) == 2
    assert [item["status"] for item in result["files"]] == ["exists", "exists"]
