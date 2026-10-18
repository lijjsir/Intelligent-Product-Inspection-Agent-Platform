"""Exercise the real local demo APIs without printing passwords or tokens."""
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from uuid import NAMESPACE_URL, uuid5
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".codex_tmp" / "piap_quality_demo"
BASE = "http://127.0.0.1:18010/api/v1"


def request(path, *, token=None, body=None, org=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = "Bearer " + token
    if org: headers["X-Org-Id"] = org
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as response:
        raw = response.read()
        try:
            value = json.loads(raw)
        except ValueError:
            value = {"message": raw.decode("utf-8", errors="replace")[:200]}
        return response.code, value
    content = response.read()
    return response.status, json.loads(content) if "json" in response.headers.get("Content-Type", "") else content


def envelope(path, **kwargs):
    status, value = request(path, **kwargs)
    assert status == 200, f"{path}: unexpected HTTP {status}"
    return value["data"]


def main():
    credentials = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
    untouched = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                 [ROOT / "backend/.env", ROOT / "frontend/.env.local"] if path.exists()}
    mode = envelope("/runtime-context?demo=0&execution_mode=business")
    assert mode["execution_mode"] == "demo" and mode["case_code"] == "DEMO-QS-001"
    sessions = {}
    for account in credentials["accounts"]:
        login = envelope("/auth/token", org=credentials["organization"], body={"username": account["username"], "password": account["password"]})
        me = envelope("/users/me", token=login["access_token"])
        assert me["role"] == account["role"] and me["username"] == account["username"]
        sessions[account["username"]] = login
    assert len({value["user_id"] for value in sessions.values()}) == 3
    admin, analyst, reviewer = [sessions[name]["access_token"] for name in ("demo_admin", "demo_analyst", "demo_reviewer")]
    users = envelope("/users?page=1&size=20", token=admin)
    assert users["total"] == 3
    for token in [analyst, reviewer]:
        assert request("/users?page=1&size=20", token=token)[0] == 403
    cases = envelope("/risk-cases?page=1&size=20", token=analyst)
    assert cases["total"] >= 1
    case_id = str(uuid5(NAMESPACE_URL, "piap-quality-demo:case"))
    before = envelope(f"/risk-cases/{case_id}/workspace", token=reviewer)
    seed_ids = {str(uuid5(NAMESPACE_URL, f"piap-quality-demo:record-{index}")) for index in range(1, 4)}
    assert seed_ids <= {item["id"] for item in before["records"]} and len(before["assessment_versions"]) >= 1
    initial_total_records = envelope("/quality-data/records?page=1&size=1", token=analyst)["total"]
    assert {item["data_nature"] for item in before["records"]} == {"synthetic"}
    assert len({item["product_ref"]["product_id"] for item in before["records"]}) == 1
    initial = envelope(f"/risk-assessments/{str(uuid5(NAMESPACE_URL, 'piap-quality-demo:assessment-1'))}", token=reviewer)
    assert initial["reviewed_by"] is None  # Bootstrap never supplies a review.
    assert before["latest_assessment"]["status"] != "accepted"
    assert before["latest_assessment"]["probability"] is None
    assert request(f"/risk-cases/{case_id}/reviews", token=reviewer,
                   body={"decision": "accept", "comment": "演示不能形成正式结论"})[0] in {400, 422}
    assert envelope("/quality-supervision/sampling-candidates", token=reviewer)["items"] == []
    attachments = [item for row in before["records"] for item in row["attachment_ids"]]
    assert attachments
    status, content = request(f"/quality-data/attachments/{attachments[0]}/download", token=reviewer)
    assert status == 200 and "不是实际检测报告" in content.decode("utf-8")
    # Re-run the real bootstrap twice. Existing work and passwords must survive.
    command = [sys.executable, str(ROOT / "deploy/quality-demo/manage.py"), "seed"]
    for _ in range(2):
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
    after = envelope(f"/risk-cases/{case_id}/workspace", token=reviewer)
    assert [row["id"] for row in after["records"]] == [row["id"] for row in before["records"]]
    assert after["assessment_versions"] == before["assessment_versions"]
    assert envelope("/users?page=1&size=20", token=admin)["total"] == 3
    assert envelope("/quality-data/records?page=1&size=1", token=analyst)["total"] == initial_total_records
    for path, digest in untouched.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    result = {"stage": 1, "passed": True, "api_mode": "real_local_demo_server", "execution_mode": "demo",
        "url": credentials["url"], "accounts": 3, "cases": cases["total"], "source_records": len(before["records"]), "assessment_versions": len(before["assessment_versions"]),
        "idempotent_initialization": True, "role_boundaries_verified": True, "formal_risk_confirmation_blocked": True,
        "existing_env_files_unchanged": True, "real_model_verified": False, "remote_server_modified": False}
    (RUNTIME / "api-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
