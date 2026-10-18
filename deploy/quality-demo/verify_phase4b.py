"""Real local same-unit collaboration checks. Never modifies risk conclusions."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from verify import RUNTIME, envelope, request


def main():
    config = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
    browser = json.loads((RUNTIME / "phase4b-browser-acceptance.json").read_text(encoding="utf-8"))
    tokens, sessions = {}, {}
    for name in ("demo_analyst", "demo_reviewer", "demo_admin"):
        account = next(a for a in config["accounts"] if a["username"] == name)
        sessions[name] = envelope("/auth/token", org=config["organization"], body={"username": name, "password": account["password"]})
        tokens[name] = sessions[name]["access_token"]
    author, peer, admin = tokens.values()
    case, link_id = browser["case_id"], browser["collaboration_id"]
    before = envelope(f"/risk-cases/{case}/workspace", token=author)
    detail = envelope(f"/risk-collaborations/{link_id}", token=author)
    assert detail["basis_current"] and detail["assessment_id"] == browser["assessment_id"]
    assert detail["status"] == "done" and detail["execution_mode"] == "demo"
    assert not any("演示私聊" in message["content"] for message in detail["discussion"])
    assert any("演示公开意见" in message["content"] for message in detail["discussion"])
    body = {"assessment_id": detail["assessment_id"], "expected_basis_hash": before["latest_assessment"]["demo_validation"]["basis_hash"],
        "request_key": str(uuid4()), "coordinator_id": detail["coordinator_id"], "purpose": detail["purpose"]}
    def repeat(_): return envelope(f"/risk-cases/{case}/collaborations", token=author, body=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        repeated = list(pool.map(repeat, range(2)))
    assert {r["id"] for r in repeated} == {link_id} and all(r["reused"] for r in repeated)
    assert len(envelope(f"/risk-cases/{case}/collaborations", token=author)) == 1
    assert request(f"/risk-collaborations/{link_id}", token=admin)[0] == 403
    room = envelope(f"/meetings/rooms/{detail['room_id']}", token=peer)
    assert room["business_context"]["risk_assessment_id"] == detail["assessment_id"]
    assert request("/meetings/rooms/join", token=admin, body={"access_code": room["access_code"]})[0] == 403
    assert request(f"/meetings/rooms/{detail['room_id']}", token=author, body={"visibility": "org"}, method="PUT")[0] == 422
    assert request(f"/meetings/rooms/{detail['room_id']}", token=author, body={"business_context": {}}, method="PUT")[0] == 422
    assert request(f"/risk-cases/{case}/collaborations", token=author, body={**body, "coordinator_id": sessions["demo_admin"]["user_id"]})[0] == 422
    assert request(f"/risk-cases/{case}/collaborations", token=author, body={**body, "assessment_id": before["assessment_versions"][-1]["id"]})[0] == 409
    work = envelope(f"/collab/work-items?view=processed&item_type=action_request", token=peer)
    card = next(i for i in work if i["resource_id"] == detail["message_id"])
    assert card["payload"]["source_context"]["risk_assessment_id"] == detail["assessment_id"]
    assert card["status"] == "done" and not card["allowed_actions"]
    assert request(f"/collab/threads/{detail['thread_id']}", token=author, method="DELETE")[0] == 422
    assert request(f"/meetings/rooms/{detail['room_id']}", token=author, method="DELETE")[0] == 422
    assert request(f"/collab/messages/{detail['message_id']}", token=author, method="DELETE")[0] == 422
    after = envelope(f"/risk-cases/{case}/workspace", token=author)
    assert before["latest_assessment"]["demo_workflow"] == after["latest_assessment"]["demo_workflow"]
    assert before["assessment_versions"] == after["assessment_versions"]
    assert before["case"] == after["case"]
    assert not envelope("/quality-supervision/sampling-candidates", token=peer)["items"]
    result = {"stage": "4b", "passed": True, "api_mode": "real_local_mysql", "case_id": case, "collaboration_id": link_id,
        "room_id": detail["room_id"], "assessment_id": detail["assessment_id"], "version_pinned": True,
        "concurrent_repeat_same_collaboration": True, "uninvited_room_code_blocked": True,
        "context_rebinding_blocked": True, "private_messages_excluded": True, "trace_records_protected": True,
        "assessment_unchanged": True, "formal_candidates_empty": True, "real_model_called": False}
    (RUNTIME / "phase4b-api-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
