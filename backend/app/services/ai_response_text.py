from __future__ import annotations

import json
import re
from typing import Any


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def normalize_ai_response_content(content: Any) -> tuple[str, dict[str, str]]:
    """Return user-facing text from an AI response that may be a JSON payload."""
    text = str(content or "").strip()
    parsed = _extract_json_object(text) or _extract_bare_answer_summary(text)
    if not parsed:
        return text, {}

    answer = parsed.get("answer")
    summary = parsed.get("summary")
    display = answer if isinstance(answer, str) and answer.strip() else None
    if display is None and isinstance(parsed.get("text"), str) and parsed["text"].strip():
        display = parsed["text"]
    if display is None and isinstance(summary, str) and summary.strip():
        display = summary
    if display is None:
        return text, {}

    metadata: dict[str, str] = {"response_format": "answer_summary_json"}
    if isinstance(summary, str) and summary.strip():
        metadata["summary"] = summary.strip()
    return display.strip(), metadata


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    candidates = [text.strip()]
    candidates.extend(block.strip() for block in _JSON_BLOCK_RE.findall(text))
    candidates.extend(_json_spans(text))

    candidates.sort(key=lambda value: ('"answer"' not in value, len(value)))
    for candidate in candidates:
        if not candidate:
            continue
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = _extract_loose_json_object(candidate)
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_loose_json_object(text: str) -> dict[str, str] | None:
    if not re.search(r"""["']?answer["']?\s*:""", text, re.IGNORECASE):
        return None
    answer = _extract_loose_string_field(text, "answer")
    summary = _extract_loose_string_field(text, "summary")
    text_field = _extract_loose_string_field(text, "text")
    if not answer and not summary and not text_field:
        return None
    payload: dict[str, str] = {}
    if answer:
        payload["answer"] = answer
    if summary:
        payload["summary"] = summary
    if text_field:
        payload["text"] = text_field
    return payload


def _extract_bare_answer_summary(text: str) -> dict[str, str] | None:
    if not re.match(r"\s*(?:answer|summary|text)\s*[:：]", text, re.IGNORECASE):
        return None
    answer = _extract_bare_string_field(text, "answer")
    summary = _extract_bare_string_field(text, "summary")
    text_field = _extract_bare_string_field(text, "text")
    if not answer and not summary and not text_field:
        return None
    payload: dict[str, str] = {}
    if answer:
        payload["answer"] = answer
    if summary:
        payload["summary"] = summary
    if text_field:
        payload["text"] = text_field
    return payload


def _extract_loose_string_field(text: str, field: str) -> str:
    pattern = re.compile(
        rf"""["']?{re.escape(field)}["']?\s*:\s*["']"""
        r"""(.*?)"""
        r"""(?=["']?\s*,\s*["']?(?:answer|summary|text|message_type|ui_schema|rag_summary|citations|quality|metadata)["']?\s*:|["']?\s*}\s*$)""",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text.strip())
    if not match:
        return ""
    return _decode_loose_json_string(match.group(1)).strip()


def _extract_bare_string_field(text: str, field: str) -> str:
    pattern = re.compile(
        rf"(?:^|\n)\s*{re.escape(field)}\s*[:：]\s*"
        r"(.*?)"
        r"(?=\n\s*(?:answer|summary|text|message_type|ui_schema|rag_summary|citations|quality|metadata)\s*[:：]|$)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text.strip())
    return match.group(1).strip() if match else ""


def _decode_loose_json_string(value: str) -> str:
    escaped = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    try:
        return str(json.loads(f'"{escaped}"'))
    except json.JSONDecodeError:
        return value.replace("\\n", "\n").replace('\\"', '"')


def _json_spans(text: str) -> list[str]:
    spans: list[str] = []
    for match in re.finditer(r"\{", text):
        depth = 0
        in_string = False
        escaped = False
        for index in range(match.start(), len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\" and in_string:
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    spans.append(text[match.start(): index + 1])
                    break
    return spans
