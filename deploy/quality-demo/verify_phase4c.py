"""Repeatable real local checks for isolated demo sampling suggestions."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from verify import RUNTIME, envelope, request


def main():
    config = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
    browser = json.loads((RUNTIME / "phase4c-browser-acceptance.json").read_text(encoding="utf-8"))
    concurrency = json.loads((RUNTIME / "phase4c-concurrency.json").read_text(encoding="utf-8"))
    assert concurrency["save_statuses"] == [200, 409]
    tokens = {}
    for name in ("demo_analyst", "demo_reviewer", "demo_admin"):
        account = next(a for a in config["accounts"] if a["username"] == name)
        tokens[name] = envelope("/auth/token", org=config["organization"], body={"username":name,"password":account["password"]})["access_token"]
    author, peer, admin = tokens.values()
    case, suggestion_id = browser["case_id"], browser["suggestion_id"]
    path = "/demo-sampling/suggestions/" + suggestion_id
    before = envelope(f"/risk-cases/{case}/workspace", token=author)
    row = envelope(path, token=author)
    assert row["status"] == "demo_confirmed" and row["is_current"]
    assert row["snapshot"]["assessment_id"] == before["latest_assessment"]["id"]
    assert row["snapshot"]["review"]["reviewed_by"] != before["latest_assessment"]["submitted_by"]
    assert row["snapshot"]["llm_called"] is False
    assert row["execution_mode"] == "demo" and row["snapshot"]["execution_mode"] == "demo"
    assert any("演示公开意见" in m["content"] for m in row["snapshot"]["opinions"])
    assert not any("演示私聊" in m["content"] for m in row["snapshot"]["opinions"])
    assert all(row["content"][k] is None for k in ("sample_quantity","batch","location","proposed_time"))
    candidate = envelope("/demo-sampling/candidates?case_id=" + case, token=author)["items"][0]
    body = {"assessment_id":candidate["snapshot"]["assessment_id"], "collaboration_id":candidate["snapshot"]["collaboration_id"], "expected_context_hash":candidate["context_hash"]}
    def repeat(_): return envelope(f"/risk-cases/{case}/demo-sampling-suggestions", token=author, body=body)
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(repeat,range(2)))
    assert all(r["id"] == suggestion_id and r["reused"] for r in results)
    assert len(envelope("/demo-sampling/suggestions?case_id=" + case, token=author)) == 1
    assert request(path, token=admin)[0] == 403
    assert request("/demo-sampling/candidates", token=admin)[0] == 403
    assert request(path, token=peer, method="PATCH", body={"expected_revision":row["revision"],"content":row["content"]})[0] == 403
    assert request(path, token=author, method="PATCH", body={"expected_revision":row["revision"],"content":row["content"]})[0] == 409
    assert request(path + "/confirm", token=author, body={"expected_revision":row["revision"]})[0] == 409
    assert request(f"/risk-cases/{case}/demo-sampling-suggestions", token=author, body={**body,"expected_context_hash":"0"*64})[0] == 409
    assert request(f"/risk-cases/{case}/demo-sampling-suggestions", token=author, body={**body,"assessment_id":str(uuid4())})[0] == 409
    assert request(f"/risk-cases/{case}/demo-sampling-suggestions", token=author, body={**body,"collaboration_id":str(uuid4())})[0] == 404
    assert request(f"/risk-cases/{case}/demo-sampling-suggestions", token=author, body={**body,"execution_mode":"business"})[0] == 422
    assert request(path, token=author, method="DELETE")[0] == 405
    assert not envelope("/quality-supervision/sampling-candidates",token=peer)["items"]
    assert envelope("/sampling-plans",token=peer)["total"] == 0
    after = envelope(f"/risk-cases/{case}/workspace",token=author)
    assert before["case"] == after["case"] and before["assessment_versions"] == after["assessment_versions"]
    assert row == envelope(path,token=peer)  # Both invited experts see the same frozen suggestion.
    result = {"stage":"4c","passed":True,"api_mode":"real_local_mysql","case_id":case,"suggestion_id":suggestion_id,
        "concurrent_create_reuses_one":True,"optimistic_save_statuses":[200,409],"fixed_content_protected":True,
        "admin_and_other_author_writes_blocked":True,"stale_context_and_wrong_version_blocked":True,
        "private_messages_excluded":True,"unknown_fields_remain_null":True,"assessment_unchanged":True,
        "formal_candidates_empty":True,"formal_sampling_plans_empty":True,"real_model_called":False}
    (RUNTIME/"phase4c-api-acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


if __name__ == "__main__": main()
