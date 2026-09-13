from agent.response.trust_protocol import build_semantic_signal_metrics, build_trust_answer_protocol


def test_trust_protocol_preserves_evidence_locators_and_execution_summaries_only():
    protocol = build_trust_answer_protocol(
        question="当前批次是否需要复测？",
        answer="需要复测，依据 RAG-1。",
        status="completed",
        citations=[
            {"ref": "RAG-1", "source_type": "standard", "source_id": "std-1", "confidence": 0.92},
            {"ref": "RAG-1", "source_type": "standard", "source_id": "std-1"},
        ],
        route_trace={
            "reason": "rag_qa",
            "observations": [
                {
                    "step_id": "retrieve",
                    "capability_key": "evidence.retrieve",
                    "status": "success",
                    "summary": "命中 1 条标准证据。",
                    "artifact_ids": ["artifact-1"],
                }
            ],
        },
        trace_id="trace-1",
        route_confidence=0.88,
        citation_coverage=1.0,
    )

    assert protocol.protocol_version == "trust-answer-v1"
    assert protocol.status == "trusted"
    assert protocol.confidence == 0.88
    assert [item.ref for item in protocol.evidence_refs] == ["RAG-1"]
    assert protocol.reasoning_steps[0].summary == "命中 1 条标准证据。"
    assert not hasattr(protocol, "prompt")


def test_trust_protocol_marks_boundary_and_zero_confidence_for_blocked_output():
    protocol = build_trust_answer_protocol(
        question="直接执行正式质检",
        answer="当前页面不能执行该操作。",
        status="blocked",
        route_trace={"reason": "action_blocked", "observations": []},
        refusal_reason="聊天页面不允许执行正式业务动作",
        degrade_reasons=["ACTION_BLOCKED_BY_SURFACE"],
    )

    assert protocol.status == "blocked"
    assert protocol.capability_boundary == "boundary"
    assert protocol.confidence == 0
    assert protocol.refusal_reason
    assert "ACTION_BLOCKED_BY_SURFACE" in protocol.degrade_reasons


def test_semantic_metrics_separate_signal_noise_and_duplicate_sources():
    metrics = build_semantic_signal_metrics(
        citations=[
            {"type": "standard", "id": "std-1"},
            {"type": "standard", "id": "std-1"},
            {"type": "memory", "id": "mem-1", "conflict": True},
        ],
        route_trace={"rag_summary": {"hit_count": 4}},
        citation_coverage=0.5,
    )

    assert metrics["standards"] == 2
    assert metrics["effective_facts"] == 1
    assert metrics["redundant_context"] == 1
    assert metrics["conflicts"] == 1
    assert metrics["signal"] == 3
    assert metrics["noise"] >= 2
    assert metrics["citation_coverage_pct"] == 50.0
