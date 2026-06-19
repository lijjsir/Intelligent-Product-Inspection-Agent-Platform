from pathlib import Path

import pytest


def test_build_dry_run_summary_reports_six_libraries_and_seventeen_files():
    from scripts.seed_standard_libraries_by_domain import build_dry_run_summary

    summary = build_dry_run_summary(
        org_id="org-1",
        base_root=Path("/app/backend/standard/current"),
        replace_aggregate=True,
        reindex=True,
    )

    assert summary["dry_run"] is True
    assert summary["org_id"] == "org-1"
    assert summary["library_count"] == 6
    assert summary["file_count"] == 17
    assert summary["replace_aggregate"] is True
    assert summary["reindex"] is True
    assert [item["domain"] for item in summary["libraries"]] == [
        "日用陶瓷",
        "包装印刷",
        "包装材料",
        "纺织服装",
        "家具木制品",
        "通用质检",
    ]
    assert summary["libraries"][0]["rag_space_name"] == "日用陶瓷标准库空间"
    assert summary["libraries"][0]["product_category"] is None
    assert summary["libraries"][0]["pdf_root_dir"] == "/app/backend/standard/current/ceramic"
    assert summary["libraries"][4]["pdf_root_dir"] == "/app/backend/standard/current/furniture-wood"


def test_seed_script_rejects_failed_index_results_before_replacing_aggregate():
    from scripts.seed_standard_libraries_by_domain import assert_index_result_success

    with pytest.raises(RuntimeError, match="日用陶瓷标准库"):
        assert_index_result_success(
            library_name="日用陶瓷标准库",
            index_result={"failed_count": 4, "indexed_document_count": 0},
        )
