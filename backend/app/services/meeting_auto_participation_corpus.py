from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


DATASET_NAME = "meeting-auto-participation-v1"
ALLOWED_ROLES = {"user", "expert", "algorithm_engineer", "platform_operator"}
DECISIONS = {"silent", "observe", "participate"}
TRIGGERS = {"none", "evidence_gap", "unresolved_conflict", "history_conflict"}
ACTIONS = {"none", "evidence_query", "clarify", "standard_remind"}


@dataclass(frozen=True)
class Turn:
    role: str
    speaker: str
    content: str


def default_bindings() -> dict[str, list[str]]:
    return {
        "task_ids": [f"task-v1-{index:02d}" for index in range(1, 9)],
        "product_ids": [f"product-v1-{index:02d}" for index in range(1, 9)],
        "batch_nos": [f"batch-v1-{index:02d}" for index in range(1, 9)],
        "standard_ids": [f"standard-v1-{index:02d}" for index in range(1, 9)],
        "memory_ids": [f"memory-v1-{index:02d}" for index in range(1, 9)],
    }


def build_corpus(bindings: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    refs = _normalize_bindings(bindings or default_bindings())
    samples: list[dict[str, Any]] = []
    builders = (
        _evidence_pair,
        _human_handling_pair,
        _history_pair,
        _duplicate_pair,
        _quality_vs_chat_pair,
    )
    for category_index, builder in enumerate(builders):
        for local_index in range(8):
            pair_index = category_index * 8 + local_index + 1
            entity_refs = _entity_refs(refs, local_index)
            split = "dev" if local_index < 4 else "test"
            pair = builder(pair_index, split, entity_refs)
            samples.extend(pair)
    validate_corpus(samples)
    return samples


def validate_corpus(samples: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    if len(samples) != 80:
        errors.append(f"expected 80 samples, got {len(samples)}")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names: set[str] = set()
    split_groups: dict[str, set[str]] = defaultdict(set)
    category_counts: Counter[str] = Counter()

    for sample in samples:
        name = str(sample.get("sample_name") or "")
        if not name or name in names:
            errors.append(f"duplicate or empty sample_name: {name}")
        names.add(name)
        annotation = sample.get("annotation_data") or {}
        pair_id = str(annotation.get("pair_id") or "")
        split = str(annotation.get("split") or "")
        category = str(annotation.get("category") or "")
        groups[pair_id].append(sample)
        split_groups[split].add(pair_id)
        category_counts[category] += 1

        turns = sample.get("turns") or []
        if not 6 <= len(turns) <= 12:
            errors.append(f"{name}: dialogue must contain 6 to 12 turns")
        for turn in turns:
            if turn.get("role") not in ALLOWED_ROLES:
                errors.append(f"{name}: invalid role {turn.get('role')}")
        if annotation.get("correct_decision") not in DECISIONS:
            errors.append(f"{name}: invalid decision")
        if annotation.get("trigger_type") not in TRIGGERS:
            errors.append(f"{name}: invalid trigger type")
        if annotation.get("action_type") not in ACTIONS:
            errors.append(f"{name}: invalid action type")
        evidence_turns = annotation.get("evidence_turns") or []
        if any(not isinstance(value, int) or value < 1 or value > len(turns) for value in evidence_turns):
            errors.append(f"{name}: evidence turn outside dialogue")
        if not str(sample.get("text_content") or "").strip():
            errors.append(f"{name}: empty text_content")
        entity_refs = sample.get("source_metadata", {}).get("entity_refs") or {}
        if any(not str(value).strip() for value in entity_refs.values()):
            errors.append(f"{name}: empty entity reference")

    if len(groups) != 40:
        errors.append(f"expected 40 contrast groups, got {len(groups)}")
    if split_groups.get("dev", set()) & split_groups.get("test", set()):
        errors.append("a contrast group appears in both dev and test")
    if len(split_groups.get("dev", set())) != 20 or len(split_groups.get("test", set())) != 20:
        errors.append("expected 20 dev groups and 20 test groups")
    if any(count != 16 for count in category_counts.values()) or len(category_counts) != 5:
        errors.append(f"expected 16 samples in each of five categories, got {dict(category_counts)}")

    for pair_id, pair in groups.items():
        if len(pair) != 2:
            errors.append(f"{pair_id}: contrast group must contain two samples")
            continue
        left, right = pair
        if left["annotation_data"].get("split") != right["annotation_data"].get("split"):
            errors.append(f"{pair_id}: pair crosses splits")
        left_turns = left.get("turns") or []
        right_turns = right.get("turns") or []
        if len(left_turns) != len(right_turns):
            errors.append(f"{pair_id}: pair dialogue length differs")
            continue
        changed = sum(
            1
            for first, second in zip(left_turns, right_turns)
            if (first.get("role"), first.get("speaker"), first.get("content"))
            != (second.get("role"), second.get("speaker"), second.get("content"))
        )
        if changed != 1:
            errors.append(f"{pair_id}: expected exactly one changed turn, got {changed}")

    if errors:
        raise ValueError("invalid meeting auto participation corpus:\n- " + "\n- ".join(errors))
    return {
        "sample_count": len(samples),
        "group_count": len(groups),
        "dev_groups": len(split_groups["dev"]),
        "test_groups": len(split_groups["test"]),
        "category_counts": dict(category_counts),
    }


def evaluate_predictions(
    samples: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    *,
    split: str = "test",
) -> dict[str, float | int]:
    selected = [item for item in samples if item["annotation_data"].get("split") == split]
    rows = [
        (item, predictions.get(str(item["sample_name"]), {"decision": "silent"}))
        for item in selected
    ]
    gold_positive = sum(item["annotation_data"]["correct_decision"] == "participate" for item, _ in rows)
    predicted_positive = sum(str(pred.get("decision") or "silent") == "participate" for _, pred in rows)
    true_positive = sum(
        item["annotation_data"]["correct_decision"] == "participate"
        and str(pred.get("decision") or "silent") == "participate"
        for item, pred in rows
    )
    precision = _safe_div(true_positive, predicted_positive)
    recall = _safe_div(true_positive, gold_positive)
    trigger_f1 = _safe_div(2 * precision * recall, precision + recall)
    false_interruptions = sum(
        item["annotation_data"]["correct_decision"] != "participate"
        and str(pred.get("decision") or "silent") == "participate"
        for item, pred in rows
    )
    missed = sum(
        item["annotation_data"]["correct_decision"] == "participate"
        and str(pred.get("decision") or "silent") != "participate"
        for item, pred in rows
    )
    negative_count = len(rows) - gold_positive

    action_scores = [
        _class_f1(
            [item["annotation_data"]["correct_decision"] for item, _ in rows],
            [str(pred.get("decision") or "silent") for _, pred in rows],
            label,
        )
        for label in sorted(DECISIONS)
    ]
    target_rows = [
        (item, pred)
        for item, pred in rows
        if item["annotation_data"]["correct_decision"] == "participate"
    ]
    target_accuracy = _safe_div(
        sum(
            str(pred.get("target_role") or "") == str(item["annotation_data"].get("target_role") or "")
            for item, pred in target_rows
        ),
        len(target_rows),
    )
    evidence_accuracy = _safe_div(
        sum(_evidence_correct(item, pred) for item, pred in target_rows),
        len(target_rows),
    )
    cancellation_rows = [
        (item, pred)
        for item, pred in rows
        if "human_is_handling" in list(item["annotation_data"].get("suppression_reasons") or [])
    ]
    cancellation_accuracy = _safe_div(
        sum(str(pred.get("decision") or "silent") == "silent" for _, pred in cancellation_rows),
        len(cancellation_rows),
    )
    return {
        "sample_count": len(rows),
        "trigger_precision": round(precision, 6),
        "trigger_recall": round(recall, 6),
        "trigger_f1": round(trigger_f1, 6),
        "false_interruption_rate": round(_safe_div(false_interruptions, negative_count), 6),
        "missed_trigger_rate": round(_safe_div(missed, gold_positive), 6),
        "behavior_macro_f1": round(sum(action_scores) / len(action_scores), 6),
        "target_role_accuracy": round(target_accuracy, 6),
        "evidence_reference_accuracy": round(evidence_accuracy, 6),
        "observe_cancellation_accuracy": round(cancellation_accuracy, 6),
    }


def evaluate_methods(
    samples: list[dict[str, Any]],
    predictions_by_method: dict[str, dict[str, dict[str, Any]]],
    *,
    split: str = "test",
) -> dict[str, dict[str, float | int]]:
    required = {"fixed_rules", "raw_transcript_llm", "full_context_memory"}
    missing = sorted(required - set(predictions_by_method))
    if missing:
        raise ValueError(f"missing prediction methods: {', '.join(missing)}")
    results = {
        method: evaluate_predictions(samples, predictions, split=split)
        for method, predictions in predictions_by_method.items()
    }
    target_recall = float(results["full_context_memory"]["trigger_recall"])
    for method, predictions in predictions_by_method.items():
        results[method]["matched_recall_false_interruption_rate"] = round(
            _false_interruption_at_target_recall(
                samples,
                predictions,
                target_recall=target_recall,
                split=split,
            ),
            6,
        )
    return results


def select_confidence_threshold(
    samples: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    *,
    split: str = "dev",
) -> float:
    selected = [item for item in samples if item["annotation_data"].get("split") == split]
    candidates = sorted(
        {
            0.0,
            1.0,
            *(
                max(0.0, min(1.0, float(predictions.get(item["sample_name"], {}).get("confidence", 0.0))))
                for item in selected
            ),
        }
    )
    best_threshold = 0.75
    best_f1 = -1.0
    for threshold in candidates:
        thresholded = {
            item["sample_name"]: {
                **predictions.get(item["sample_name"], {}),
                "decision": (
                    "participate"
                    if float(predictions.get(item["sample_name"], {}).get("confidence", 0.0)) >= threshold
                    else "silent"
                ),
            }
            for item in selected
        }
        f1 = float(evaluate_predictions(selected, thresholded, split=split)["trigger_f1"])
        if f1 > best_f1 or (f1 == best_f1 and abs(threshold - 0.75) < abs(best_threshold - 0.75)):
            best_f1 = f1
            best_threshold = threshold
    return round(best_threshold, 6)


async def seed_text_dataset(
    session: Any,
    *,
    org_id: str,
    user_id: str,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    from app.schemas.dataset import DatasetCreateRequest, DatasetSampleCreateRequest
    from app.services.dataset_service import DatasetService

    validate_corpus(samples)
    service = DatasetService(session, org_id, user_id)
    existing = await service.list_datasets(
        page=1,
        size=100,
        keyword=DATASET_NAME,
        modality="text",
        status="active",
    )
    dataset = next((item for item in existing.items if item.name == DATASET_NAME), None)
    if dataset is None:
        dataset = await service.create_dataset(
            DatasetCreateRequest(
                name=DATASET_NAME,
                description="会议Agent主动参与V1的40组最小对照文本语料。",
                modality="text",
                tags=["meeting-agent", "auto-participation", "contrast-pair", "v1"],
            )
        )
    existing_samples = await service.list_samples(
        dataset_id=str(dataset.id),
        page=1,
        size=100,
        sample_type="text",
    )
    existing_names = {str(item.sample_name or "") for item in existing_samples.items}
    created = 0
    for sample in samples:
        if sample["sample_name"] in existing_names:
            continue
        await service.create_text_sample(
            dataset_id=str(dataset.id),
            payload=DatasetSampleCreateRequest(
                sample_name=sample["sample_name"],
                text_content=sample["text_content"],
                annotation_data=sample["annotation_data"],
                related_entities=sample["related_entities"],
                source_metadata=sample["source_metadata"],
            ),
        )
        created += 1
    await session.commit()
    return {"dataset_id": str(dataset.id), "created": created, "total": len(samples)}


def _evidence_pair(pair_index: int, split: str, refs: dict[str, str]) -> list[dict[str, Any]]:
    base = _base_turns(refs)
    missing = [*base]
    complete = [*base]
    missing[4] = Turn("platform_operator", "平台运营", f"任务 {refs['task_id']} 只有口头结论，原始证据还没挂上。")
    complete[4] = Turn("platform_operator", "平台运营", f"任务 {refs['task_id']} 的失败规则、缺陷和人工复核记录都已挂上。")
    return [
        _sample(pair_index, "evidence_gap", split, "missing", missing, refs, "participate", "evidence_gap", "evidence_query", "platform_operator", [2, 5, 6], []),
        _sample(pair_index, "evidence_gap", split, "complete", complete, refs, "silent", "none", "none", None, [2, 5], ["evidence_complete"]),
    ]


def _human_handling_pair(pair_index: int, split: str, refs: dict[str, str]) -> list[dict[str, Any]]:
    base = _base_turns(refs)
    unattended = [*base]
    handled = [*base]
    unattended[5] = Turn("user", "产品负责人", "两边说法不一致，先按原计划走，没人再跟了。")
    handled[5] = Turn("user", "产品负责人", "两边说法不一致，我现在协调双方逐项核对，结论先不定。")
    return [
        _sample(pair_index, "human_handling", split, "unattended", unattended, refs, "participate", "unresolved_conflict", "clarify", "expert", [3, 4, 6], []),
        _sample(pair_index, "human_handling", split, "handled", handled, refs, "silent", "unresolved_conflict", "none", "expert", [3, 4, 6], ["human_is_handling"]),
    ]


def _history_pair(pair_index: int, split: str, refs: dict[str, str]) -> list[dict[str, Any]]:
    base = _base_turns(refs)
    active = [*base]
    superseded = [*base]
    active[3] = Turn("expert", "质量专家", f"记忆 {refs['memory_id']} 仍是 active，要求失败批次不得直接放行。")
    superseded[3] = Turn("expert", "质量专家", f"记忆 {refs['memory_id']} 已 superseded，新版本允许人工复核后放行。")
    return [
        _sample(pair_index, "history_status", split, "active", active, refs, "participate", "history_conflict", "standard_remind", "user", [4, 6], []),
        _sample(pair_index, "history_status", split, "superseded", superseded, refs, "silent", "none", "none", None, [4, 6], ["history_superseded"]),
    ]


def _duplicate_pair(pair_index: int, split: str, refs: dict[str, str]) -> list[dict[str, Any]]:
    base = _base_turns(refs)
    first = [*base]
    repeated = [*base]
    first[4] = Turn("platform_operator", "平台运营", "这是第一次出现证据未补齐的问题，会议Agent还没有提醒过。")
    repeated[4] = Turn("platform_operator", "平台运营", "会议Agent在三个人类轮次内已提醒过，期间没有新增证据。")
    return [
        _sample(pair_index, "duplicate_window", split, "first", first, refs, "observe", "evidence_gap", "evidence_query", "platform_operator", [2, 5], []),
        _sample(pair_index, "duplicate_window", split, "repeated", repeated, refs, "silent", "evidence_gap", "none", "platform_operator", [2, 5], ["duplicate_without_new_evidence"]),
    ]


def _quality_vs_chat_pair(pair_index: int, split: str, refs: dict[str, str]) -> list[dict[str, Any]]:
    base = _base_turns(refs)
    quality = [*base]
    chat = [*base]
    quality[5] = Turn("user", "产品负责人", f"任务 {refs['task_id']} 是高风险失败，但这批今天必须直接放行。")
    chat[5] = Turn("user", "产品负责人", "今天的组会改到三点，会议室链接保持不变。")
    return [
        _sample(pair_index, "quality_vs_chat", split, "quality_decision", quality, refs, "participate", "unresolved_conflict", "clarify", "user", [2, 3, 6], []),
        _sample(pair_index, "quality_vs_chat", split, "administrative_chat", chat, refs, "silent", "none", "none", None, [6], ["non_task_conversation"]),
    ]


def _base_turns(refs: dict[str, str]) -> list[Turn]:
    return [
        Turn("user", "产品负责人", f"今天确认产品 {refs['product_id']} 的批次 {refs['batch_no']}。"),
        Turn("platform_operator", "平台运营", f"会议已绑定质检任务 {refs['task_id']}。"),
        Turn("algorithm_engineer", "算法工程师", "当前结果使用任务中记录的模型和 Prompt 版本。"),
        Turn("expert", "质量专家", f"判定需要遵循标准 {refs['standard_id']}。"),
        Turn("platform_operator", "平台运营", "我正在核对任务结果和会议结论是否一致。"),
        Turn("user", "产品负责人", "请把今天的结论在这轮会议里定下来。"),
    ]


def _sample(
    pair_index: int,
    category: str,
    split: str,
    condition: str,
    turns: list[Turn],
    refs: dict[str, str],
    correct_decision: str,
    trigger_type: str,
    action_type: str,
    target_role: str | None,
    evidence_turns: list[int],
    suppression_reasons: list[str],
) -> dict[str, Any]:
    pair_id = f"pair-{pair_index:02d}"
    sample_name = f"{pair_id}-{category}-{condition}"
    turn_dicts = [
        {"role": turn.role, "speaker": turn.speaker, "content": turn.content}
        for turn in turns
    ]
    return {
        "sample_name": sample_name,
        "text_content": _format_dialogue(turns),
        "turns": turn_dicts,
        "annotation_data": {
            "schema_version": "meeting-auto-participation-v1",
            "pair_id": pair_id,
            "split": split,
            "category": category,
            "condition": condition,
            "correct_decision": correct_decision,
            "trigger_type": trigger_type,
            "action_type": action_type,
            "target_role": target_role,
            "evidence_turns": evidence_turns,
            "suppression_reasons": suppression_reasons,
        },
        "related_entities": list(refs.values()),
        "source_metadata": {
            "source": "meeting-auto-participation-v1-generator",
            "contrast_group": pair_id,
            "split": split,
            "entity_refs": refs,
            "quality_task_snapshot": {
                "task_id": refs["task_id"],
                "status": "succeeded",
                "verdict": "fail",
                "overall_score": 61,
                "risk_level": "high",
                "failed_rules": ["release_requires_review"],
                "root_cause": "关键证据或人工复核未闭环",
                "defects": [{"type": "quality_gate", "severity": "major"}],
                "manual_review": {"status": "pending"},
                "model_key": "bound-task-model",
                "prompt_version": "bound-task-prompt",
            },
        },
    }


def _format_dialogue(turns: list[Turn]) -> str:
    return "\n".join(
        f"[{9 + (index // 6):02d}:{index % 6 * 5:02d}] {turn.role}/{turn.speaker}: {turn.content}"
        for index, turn in enumerate(turns)
    )


def _normalize_bindings(bindings: dict[str, list[str]]) -> dict[str, list[str]]:
    required = ("task_ids", "product_ids", "batch_nos", "standard_ids", "memory_ids")
    normalized: dict[str, list[str]] = {}
    for key in required:
        values = list(dict.fromkeys(str(item).strip() for item in bindings.get(key) or [] if str(item).strip()))
        if not values:
            raise ValueError(f"binding {key} must contain at least one existing entity id")
        normalized[key] = values
    return normalized


def _entity_refs(bindings: dict[str, list[str]], index: int) -> dict[str, str]:
    return {
        "task_id": bindings["task_ids"][index % len(bindings["task_ids"])],
        "product_id": bindings["product_ids"][index % len(bindings["product_ids"])],
        "batch_no": bindings["batch_nos"][index % len(bindings["batch_nos"])],
        "standard_id": bindings["standard_ids"][index % len(bindings["standard_ids"])],
        "memory_id": bindings["memory_ids"][index % len(bindings["memory_ids"])],
    }


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _class_f1(gold: list[str], predicted: list[str], label: str) -> float:
    true_positive = sum(g == label and p == label for g, p in zip(gold, predicted))
    false_positive = sum(g != label and p == label for g, p in zip(gold, predicted))
    false_negative = sum(g == label and p != label for g, p in zip(gold, predicted))
    precision = _safe_div(true_positive, true_positive + false_positive)
    recall = _safe_div(true_positive, true_positive + false_negative)
    return _safe_div(2 * precision * recall, precision + recall)


def _evidence_correct(sample: dict[str, Any], prediction: dict[str, Any]) -> bool:
    expected = set(int(item) for item in sample["annotation_data"].get("evidence_turns") or [])
    predicted = set(int(item) for item in prediction.get("evidence_turns") or [] if str(item).isdigit())
    return bool(predicted) and predicted <= expected


def _false_interruption_at_target_recall(
    samples: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    *,
    target_recall: float,
    split: str,
) -> float:
    selected = [item for item in samples if item["annotation_data"].get("split") == split]
    scores = {
        item["sample_name"]: float(
            predictions.get(item["sample_name"], {}).get(
                "confidence",
                1.0 if predictions.get(item["sample_name"], {}).get("decision") == "participate" else 0.0,
            )
        )
        for item in selected
    }
    thresholds = sorted({-0.001, 1.001, *scores.values()})
    gold_positive = sum(item["annotation_data"]["correct_decision"] == "participate" for item in selected)
    negatives = len(selected) - gold_positive
    candidates: list[tuple[float, float]] = []
    for threshold in thresholds:
        true_positive = sum(
            item["annotation_data"]["correct_decision"] == "participate"
            and scores[item["sample_name"]] >= threshold
            for item in selected
        )
        false_positive = sum(
            item["annotation_data"]["correct_decision"] != "participate"
            and scores[item["sample_name"]] >= threshold
            for item in selected
        )
        recall = _safe_div(true_positive, gold_positive)
        false_rate = _safe_div(false_positive, negatives)
        candidates.append((abs(recall - target_recall), false_rate))
    return min(candidates, key=lambda item: (item[0], item[1]))[1] if candidates else 0.0
