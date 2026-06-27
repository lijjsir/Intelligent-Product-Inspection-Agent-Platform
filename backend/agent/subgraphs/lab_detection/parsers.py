from __future__ import annotations

import re


_NUMBER = r"([+-]?\d+(?:\.\d+)?)"


def parse_upper_limit(limit: str | None) -> float | None:
    if not limit:
        return None
    text = str(limit).strip()
    patterns = [
        rf"(?:<=|<=|less\s+than\s+or\s+equal\s+to|not\s+greater\s+than)\s*{_NUMBER}",
        rf"(?:\u2264|\u4e0d\u5927\u4e8e|\u5c0f\u4e8e\u7b49\u4e8e)\s*{_NUMBER}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def parse_lower_limit(limit: str | None) -> float | None:
    if not limit:
        return None
    text = str(limit).strip()
    patterns = [
        rf"(?:>=|>=|greater\s+than\s+or\s+equal\s+to|not\s+less\s+than)\s*{_NUMBER}",
        rf"(?:\u2265|\u4e0d\u5c0f\u4e8e|\u5927\u4e8e\u7b49\u4e8e)\s*{_NUMBER}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def parse_numeric_range(value: str | None) -> tuple[float, float] | None:
    if not value:
        return None
    text = str(value).strip()
    match = re.search(
        rf"{_NUMBER}\s*(?:-|~|\u2013|\u2014|to|\u81f3|\u5230)\s*{_NUMBER}",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    left = float(match.group(1))
    right = float(match.group(2))
    return (min(left, right), max(left, right))
