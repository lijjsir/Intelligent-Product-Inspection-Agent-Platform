"""Reproducible evaluation tools; never infer probabilities from model confidence."""

from __future__ import annotations

import math
from statistics import median


def calibration_report(predictions: list[float], outcomes: list[int], bins: int = 10) -> dict:
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("预测与实际标签必须等长且非空")
    if bins < 1 or bins > 100:
        raise ValueError("校准区间数量无效")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in predictions) or any(
        y not in {0, 1} for y in outcomes
    ):
        raise ValueError("预测应为0–1概率，实际标签应为0或1")
    brier = sum((p - y) ** 2 for p, y in zip(predictions, outcomes)) / len(predictions)
    groups = []
    for index in range(bins):
        rows = [
            (p, y) for p, y in zip(predictions, outcomes) if min(int(p * bins), bins - 1) == index
        ]
        if not rows:
            continue
        expected = sum(p for p, y in rows) / len(rows)
        actual = sum(y for p, y in rows) / len(rows)
        groups.append(
            {
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "count": len(rows),
                "predicted": expected,
                "observed": actual,
            }
        )
    return {
        "sample_count": len(predictions),
        "brier": brier,
        "ece": sum(g["count"] * abs(g["predicted"] - g["observed"]) for g in groups)
        / len(predictions),
        "reliability_bins": groups,
        "limitations": ["需使用独立真实结果校准集，不能用评分或合成标签代替"],
    }


def response_time_report(baseline_seconds: list[float], system_seconds: list[float]) -> dict:
    if not baseline_seconds or len(baseline_seconds) != len(system_seconds):
        raise ValueError("同口径案件对照必须配对且非空")
    if any(not math.isfinite(x) or x <= 0 for x in baseline_seconds) or any(
        not math.isfinite(x) or x < 0 for x in system_seconds
    ):
        raise ValueError("耗时无效")
    baseline, system = median(baseline_seconds), median(system_seconds)

    def p90(rows):
        ordered = sorted(rows)
        return ordered[max(0, math.ceil(len(rows) * 0.9) - 1)]

    return {
        "sample_count": len(system_seconds),
        "baseline_median_seconds": baseline,
        "system_median_seconds": system,
        "baseline_p90_seconds": p90(baseline_seconds),
        "system_p90_seconds": p90(system_seconds),
        "median_reduction": (baseline - system) / baseline,
    }
