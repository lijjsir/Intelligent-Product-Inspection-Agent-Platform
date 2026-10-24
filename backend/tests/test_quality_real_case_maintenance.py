from types import SimpleNamespace

import pytest

from scripts.maintain_quality_real_case import is_confirmed_test_task


@pytest.mark.parametrize("source", [
    "chat_attachment_resolution_test", "chat_attachment_resolution_test_v2",
    "chat_attachment_resolution_test_v3", "p1p2_execution_acceptance",
    "report_task_acceptance", "formal_standard_requirement_acceptance",
])
def test_explicit_development_fixture_is_selected(source):
    assert is_confirmed_test_task(SimpleNamespace(meta_data={"source": source}))


@pytest.mark.parametrize("metadata", [
    None, {}, {"source": "task_list"},
    {"case_preparation": {"case_id": "REPORT_EBIKE_JG2128520085"}},
    {"source": "official_report_import"}, {"source": "public_dataset_research"},
])
def test_real_or_unclassified_task_is_not_deleted(metadata):
    assert not is_confirmed_test_task(SimpleNamespace(meta_data=metadata))
