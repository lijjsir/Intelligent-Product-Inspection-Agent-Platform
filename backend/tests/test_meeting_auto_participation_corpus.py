import pytest

from app.services.meeting_auto_participation_corpus import (
    build_corpus,
    evaluate_methods,
    evaluate_predictions,
    select_confidence_threshold,
    validate_corpus,
)


def test_corpus_has_40_minimal_contrast_pairs_without_split_leakage():
    samples = build_corpus()
    summary = validate_corpus(samples)

    assert summary["sample_count"] == 80
    assert summary["group_count"] == 40
    assert summary["dev_groups"] == 20
    assert summary["test_groups"] == 20
    assert set(summary["category_counts"].values()) == {16}


def test_corpus_uses_only_existing_project_roles_and_valid_evidence_turns():
    samples = build_corpus()
    allowed = {"user", "expert", "algorithm_engineer", "platform_operator"}
    for sample in samples:
        assert 6 <= len(sample["turns"]) <= 12
        assert {turn["role"] for turn in sample["turns"]} <= allowed
        assert all(1 <= turn <= len(sample["turns"]) for turn in sample["annotation_data"]["evidence_turns"])


def test_validator_rejects_pair_that_changes_more_than_one_turn():
    samples = build_corpus()
    samples[1]["turns"][0]["content"] = "额外改变一轮"
    with pytest.raises(ValueError, match="exactly one changed turn"):
        validate_corpus(samples)


def test_perfect_predictions_produce_perfect_metrics():
    samples = build_corpus()
    predictions = {
        sample["sample_name"]: {
            "decision": sample["annotation_data"]["correct_decision"],
            "target_role": sample["annotation_data"]["target_role"],
            "evidence_turns": sample["annotation_data"]["evidence_turns"],
        }
        for sample in samples
    }
    metrics = evaluate_predictions(samples, predictions)

    assert metrics["trigger_f1"] == 1
    assert metrics["false_interruption_rate"] == 0
    assert metrics["missed_trigger_rate"] == 0
    assert metrics["behavior_macro_f1"] == 1
    assert metrics["target_role_accuracy"] == 1
    assert metrics["evidence_reference_accuracy"] == 1
    assert metrics["observe_cancellation_accuracy"] == 1


def test_three_method_evaluation_requires_all_baselines():
    samples = build_corpus()
    with pytest.raises(ValueError, match="missing prediction methods"):
        evaluate_methods(samples, {"full_context_memory": {}})


def test_dev_threshold_selection_uses_only_development_split():
    samples = build_corpus()
    predictions = {
        sample["sample_name"]: {
            "confidence": 0.9 if sample["annotation_data"]["correct_decision"] == "participate" else 0.2
        }
        for sample in samples
    }
    assert select_confidence_threshold(samples, predictions) == 0.9
