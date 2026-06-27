from app.services.chat_context_service import ChatContextService


def test_build_quality_insights_groups_multi_task_risks():
    insights = ChatContextService._build_quality_insights(
        [
            {
                "task_id": "task-1",
                "product_id": "screw",
                "spec_code": "SCREW-A",
                "status": "completed",
                "verdict": "manual_required",
                "risk_level": "medium",
                "failed_rules": ["unmapped_detected_defects"],
                "defects": [{"type": "surface_scratch"}],
                "root_cause": "表面划痕置信度高，需要复核",
            },
            {
                "task_id": "task-2",
                "product_id": "screw",
                "spec_code": "SCREW-A",
                "status": "failed",
                "verdict": "fail",
                "risk_level": "high",
                "failed_rules": ["unmapped_detected_defects"],
                "defects": [{"type": "surface_scratch"}],
            },
        ]
    )

    assert insights["failed_or_risky_count"] == 2
    assert insights["product_failure_counts"]["screw"] == 2
    assert insights["failed_rule_counts"]["unmapped_detected_defects"] == 2
    assert insights["defect_type_counts"]["surface_scratch"] == 2
    assert insights["risk_warnings"]
