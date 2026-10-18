"""Real two-account manual demo workflow, version conflicts and evidence refresh."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4, uuid5, NAMESPACE_URL

from verify import RUNTIME, envelope, request

CASE = str(uuid5(NAMESPACE_URL, "piap-quality-demo:case"))


def main():
    config = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
    sessions = {}
    for name in ("demo_analyst", "demo_reviewer"):
        account = next(a for a in config["accounts"] if a["username"] == name)
        sessions[name] = envelope("/auth/token", org=config["organization"], body={"username": name, "password": account["password"]})
    author, reviewer = [sessions[n]["access_token"] for n in sessions]
    def workspace(): return envelope(f"/risk-cases/{CASE}/workspace", token=author)
    def endpoint(row, action=""): return f"/risk-cases/{CASE}/demo-drafts/{row['id']}" + ("/" + action if action else "")
    def create():
        w = workspace()
        latest = w["latest_assessment"]
        if latest.get("demo_workflow") and latest["status"] == "demo_draft" and latest["demo_validation"]["is_current"]:
            return latest
        payload = {"base_assessment_id": latest["id"] if latest else None, "expected_basis_hash": w["demo_context"]["basis_hash"], "request_key": str(uuid4())}
        first = envelope(f"/risk-cases/{CASE}/demo-drafts", token=author, body=payload)
        same = envelope(f"/risk-cases/{CASE}/demo-drafts", token=author, body=payload)
        assert first["id"] == same["id"]
        return first
    def finish(row, suffix):
        if row["status"] == "demo_draft":
            w = workspace()
            content = {"summary": "【演示 API 验收】温升数量线索需要进一步核查" + suffix,
                "reasoning": "投诉与舆情数量变化提供调查线索；参考模拟资料原文，不代表真实检测结论。",
                "limitations": "全部资料为模拟，适用标准、测量条件和实际产品状态仍未知。", "risk_level": "unknown", "risk_type": "温升异常线索",
                "cited_record_ids": [w["records"][0]["id"]], "missing_inputs": ["真实检测报告", "标准适用条件"], "recommendations": ["补充资料后重新评估"]}
            revision = row["demo_workflow"]["revision"]
            body = {"expected_revision": revision, "content": content}
            # Two browser-equivalent saves at the same revision cannot both win.
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: request(endpoint(row), token=author, body=body, method="PATCH"), range(2)))
            assert sorted(status for status, _ in results) == [200, 409]
            row = next(value["data"] for status, value in results if status == 200)
            assert request(endpoint(row, "submit"), token=author, body={"expected_revision": revision})[0] == 409
            row = envelope(endpoint(row, "submit"), token=author, body={"expected_revision": row["demo_workflow"]["revision"]})
        assert row["status"] == "demo_submitted"
        review = {"expected_revision": row["demo_workflow"]["revision"], "decision": "approve", "comment": "【演示独立复核】已核对本版本引用与限制，保留真实证据缺口" + suffix}
        assert request(endpoint(row, "review"), token=author, body=review)[0] == 403
        assert request(endpoint(row), token=author, body={"expected_revision": review["expected_revision"], "content": row["demo_workflow"]["content"]}, method="PATCH")[0] == 409
        row = envelope(endpoint(row, "review"), token=reviewer, body=review)
        assert row["status"] == row["trust_status"] == "demo_reviewed" and row["effective_status"] == "demo_reviewed"
        assert row["probability"] is None and row["model_versions"]["llm_called"] is False
        assert row["submitted_by"] != row["reviewed_by"]
        assert request(endpoint(row, "review"), token=reviewer, body=review)[0] == 409
        return row

    path = RUNTIME / "phase4a-api-acceptance.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    w = workspace()
    if previous:
        # Repeat acceptance reads the exact saved pair, without appending more
        # synthetic records or empty versions just to rerun assertions.
        old = envelope(f"/risk-assessments/{previous['reviewed_before_supplement_id']}", token=author)
        assert old["status"] == "demo_reviewed" and old["effective_status"] == "needs_reassessment"
        completed = envelope(f"/risk-assessments/{previous['latest_assessment_id']}", token=author)
        assert completed["status"] == "demo_reviewed" and completed["submitted_by"] != completed["reviewed_by"]
        assert previous["supplement_record_id"] in w["case"]["source_record_ids"]
        result = {**previous, "reused": True, "current_latest_assessment_id": w["latest_assessment"]["id"]}
    else:
        latest = w["latest_assessment"]
        first = finish(latest if latest and latest["status"] == "demo_submitted" else create(), "（补证前）")
        source = w["records"][0]
        payload = {"source_id": source["source_id"], "external_record_id": "DEMO-QS-001-P4A-SUPPLEMENT",
            "record_type": "inspection_report", "content": {"text": "【模拟补证】仅用于版本重评验收；没有真实检测数值，不是正式检测报告。"},
            "product_ref": source["product_ref"], "enterprise_ref": {"enterprise_id": str(uuid5(NAMESPACE_URL, "piap-quality-demo:enterprise"))},
            "origin_label": "阶段四人工演示验收（模拟）", "data_nature": "synthetic"}
        status, value = request("/quality-data/events", token=author, body=payload)
        assert status == 201
        record = value["data"]
        if record["id"] in first["demo_workflow"]["content"]["cited_record_ids"] or record["id"] in w["case"]["source_record_ids"]:
            # A later explicit rerun can still exercise the same material's
            # new fragment through unit tests; do not manufacture duplicates.
            raise AssertionError("Existing supplementation is already in this version; reuse the completed acceptance record")
        envelope(f"/risk-cases/{CASE}/sources", token=author, body={"source_record_ids": [record["id"]]})
        stale = envelope(f"/risk-assessments/{first['id']}", token=reviewer)
        assert stale["status"] == "demo_reviewed" and stale["effective_status"] == "needs_reassessment"
        assert stale["review_comment"] == first["review_comment"]
        second = finish(create(), "（补证后）")
        assert second["version"] == first["version"] + 1
        result = {"stage": "4a", "passed": True, "api_mode": "real_local_mysql", "mocked_requests": 0, "case_id": CASE,
            "reviewed_before_supplement_id": first["id"], "latest_assessment_id": second["id"], "supplement_record_id": record["id"],
            "versions": [first["version"], second["version"]], "two_accounts": True, "self_review_blocked": True,
            "concurrent_revision_conflict": True, "history_preserved": True, "evidence_requires_reassessment": True, "reused": False}
    assert request(f"/risk-cases/{CASE}/reviews", token=reviewer, body={"decision": "accept", "comment": "演示不能转正式"})[0] == 422
    assert request(f"/risk-cases/{CASE}/analyze", token=author, body={})[0] == 422
    assert envelope("/quality-supervision/sampling-candidates", token=reviewer)["items"] == []
    result.update(formal_candidates_empty=True, real_model_called=False)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
