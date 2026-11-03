"""Shared evidence-first output protocol for VLM SFT and evaluation.

The model emits a short observable evidence block followed by a final binary
decision.  Keeping formatting/parsing in one module prevents training,
validation, and inference from drifting apart.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


EVIDENCE_OPEN = "<evidence>"
EVIDENCE_CLOSE = "</evidence>"
DECISIONS = {"yes": "Yes", "no": "No"}


def normalize_decision(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"yes", "true", "1", "y", "是", "有"}:
        return "Yes"
    if text in {"no", "false", "0", "n", "否", "无"}:
        return "No"
    return "Unknown"


def format_evidence_answer(evidence: Any, decision: Any) -> str:
    """Format a supervised target or prompt-visible answer."""
    text = " ".join(str(evidence or "").strip().split())
    if not text:
        text = "No reliable visual evidence is available."
    normalized = normalize_decision(decision)
    if normalized == "Unknown":
        raise ValueError("evidence answer decision must be Yes or No")
    return f"{EVIDENCE_OPEN}\n{text}\n{EVIDENCE_CLOSE}\n{normalized}"


def parse_evidence_output(raw: str) -> dict[str, Any] | None:
    """Parse one evidence block followed by a final Yes/No line.

    Extra whitespace and a surrounding markdown fence are tolerated, but
    arbitrary text outside the evidence block is not treated as evidence.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:text|markdown)?\s*(.*?)```", text,
                          flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    match = re.search(
        r"<evidence>\s*(.*?)\s*</evidence>\s*([Yy][Ee][Ss]|[Nn][Oo])\s*$",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return None
    evidence = " ".join(match.group(1).strip().split())
    decision = normalize_decision(match.group(2))
    if not evidence or decision == "Unknown":
        return None
    return {
        "evidence_text": evidence,
        "has_defect": decision,
        "raw_output": raw,
    }


def is_evidence_answer(value: str) -> bool:
    return parse_evidence_output(value) is not None


def evidence_prompt(category: str = "industrial product") -> str:
    return (
        f"<image>\nInspect this {category} image. Describe only concise, observable "
        "visual evidence in an <evidence>...</evidence> block, then put the final "
        "decision on the last line as exactly Yes or No. Do not output JSON, a "
        "defect taxonomy, confidence, coordinates, or internal audit metadata. "
        "Use No when no visible abnormality is present."
    )


def evidence_from_record(record: Mapping[str, Any]) -> str:
    truth = record.get("ground_truth") or record.get("image_structured") or {}
    if not isinstance(truth, Mapping):
        truth = {}
    return format_evidence_answer(
        truth.get("evidence_summary", ""), truth.get("has_defect", "Unknown")
    )


__all__ = [
    "DECISIONS", "EVIDENCE_CLOSE", "EVIDENCE_OPEN", "evidence_from_record",
    "evidence_prompt", "format_evidence_answer", "is_evidence_answer",
    "normalize_decision", "parse_evidence_output",
]
