"""Stage-three real API acceptance, including concurrent conversion on MySQL."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL

from verify import RUNTIME, envelope, request


def did(name):
    return str(uuid5(NAMESPACE_URL, "piap-quality-demo:" + name))


def main():
    config = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
    sessions = {}
    for name in ("demo_analyst", "demo_reviewer"):
        user = next(a for a in config["accounts"] if a["username"] == name)
        sessions[name] = envelope("/auth/token", org=config["organization"], body={"username": name, "password": user["password"]})["access_token"]
    token = sessions["demo_analyst"]
    original = envelope(f"/quality-data/records/{did('record-1')}/context", token=token)["record"]
    from zoneinfo import ZoneInfo
    anchor = (datetime.fromisoformat(original["occurred_at"]).replace(tzinfo=timezone.utc) + timedelta(days=1)).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    query = {"as_of": anchor, "object_type": "product"}
    first = envelope("/market-monitoring/scan", token=token, body=query)
    second = envelope("/market-monitoring/scan", token=token, body=query)
    assert first["execution_mode"] == "demo"
    assert [g["signal_id"] for g in first["groups"]] == [g["signal_id"] for g in second["groups"]]
    complaint = next(g for g in first["groups"] if g["record_type"] == "consumer_complaint")
    opinion = next(g for g in first["groups"] if g["record_type"] == "public_opinion")
    assert complaint["status"] == "quantity_growth" and complaint["current_count"] == 6 and complaint["previous_count"] == 1
    assert opinion["status"] == "new_cluster" and opinion["growth_percent"] is None
    assert len(first["missing_time"]) >= 2 and len(first["pending_objects"]) >= 1
    before = envelope(f"/risk-cases/{did('case')}/workspace", token=token)
    def convert(who):
        return envelope(f"/market-monitoring/signals/{complaint['signal_id']}/risk-case", token=sessions[who], body={"target_case_id": did("case")})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(convert, sessions))
    assert {r["case"]["id"] for r in results} == {did("case")}
    assert sum(r["reused"] for r in results) >= 1
    # Re-associating the same sources also picks up fragments materialized
    # after initial intake, without duplicating either source records or cases.
    envelope(f"/risk-cases/{did('case')}/sources", token=token, body={"source_record_ids": complaint["source_record_ids"]})
    after = envelope(f"/risk-cases/{did('case')}/workspace", token=token)
    assert set(complaint["source_record_ids"]) <= set(after["case"]["source_record_ids"])
    assert len(after["assessment_versions"]) == len(before["assessment_versions"])
    assert after["latest_assessment"]["reviewed_by"] == before["latest_assessment"]["reviewed_by"]
    assert after["latest_assessment"]["review_comment"] == before["latest_assessment"]["review_comment"]
    focus_payload = {"object_type": "product", "object_id": did("product"), "reason": "【演示】持续观察温升数量线索"}
    focus1 = envelope("/market-monitoring/focus-objects", token=token, body=focus_payload)
    focus2 = envelope("/market-monitoring/focus-objects", token=token, body=focus_payload)
    assert focus1["id"] == focus2["id"] and focus2["reused"]
    assert len(envelope("/market-monitoring/focus-objects", token=token)) == 1
    enterprise = envelope("/market-monitoring/scan", token=token, body={**query, "object_type": "enterprise"})
    assert all(g["object_id"] == did("enterprise") for g in enterprise["groups"])
    # Without a complete 14-day declaration, the wider historical window may
    # display counts but must never infer that the absent records equal zero.
    prior = (datetime.fromisoformat(anchor) - timedelta(days=1)).date().isoformat()
    incomplete = envelope("/market-monitoring/scan", token=token, body={**query, "as_of": prior})
    assert all(g["status"] == "insufficient_coverage" and g["signal_id"] is None for g in incomplete["groups"])
    assert request("/market-monitoring/scan", token=token, body={**query, "as_of": "2100-01-01"})[0] == 422
    candidates = envelope("/quality-supervision/sampling-candidates", token=token)
    assert not candidates["items"]
    cases = envelope("/risk-cases?size=100", token=token)
    assert len(cases["items"]) == 1
    result = {"stage": 3, "passed": True, "api_mode": "real_local_mysql", "mocked_requests": 0,
              "as_of": anchor, "scenario_case_id": did("case"), "complaint_signal_id": complaint["signal_id"],
              "opinion_signal_id": opinion["signal_id"], "focus_id": focus1["id"], "separate_channels": True,
              "zero_baseline_percentage_null": True, "coverage_and_unknowns_verified": True,
              "concurrent_conversion_same_case": True, "formal_candidates_empty": True, "real_model_called": False}
    (RUNTIME / "phase3-api-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
