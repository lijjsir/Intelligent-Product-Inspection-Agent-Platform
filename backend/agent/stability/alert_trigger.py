def should_trigger(report: dict) -> bool:
    return report.get("risk_level") in {"ORANGE", "RED"}
