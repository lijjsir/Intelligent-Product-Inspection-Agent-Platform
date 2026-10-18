"""Real local stage-two acceptance. Reuses one labelled source across retries."""
import json
import urllib.request
from uuid import uuid4, uuid5, NAMESPACE_URL

from verify import ROOT, RUNTIME, BASE, envelope, request


def upload(token, name, content):
    boundary = "piap-demo-" + uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: text/plain\r\n\r\n'.encode()
            + content + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(BASE + "/quality-data/attachments", data=body, headers={
        "Authorization": "Bearer " + token, "Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=30) as response:
        assert response.status == 201
        return json.loads(response.read())["data"][0]


def import_existing(token, payload):
    boundary = "piap-demo-import-" + uuid4().hex
    data = json.dumps([payload], ensure_ascii=False).encode("utf-8")
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="request_key"\r\n\r\nphase2-known-origin-import-v1\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="stage2-origin.json"\r\nContent-Type: application/json\r\n\r\n').encode()+data+f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE+"/quality-data/imports",data=body,headers={"Authorization":"Bearer "+token,
        "Content-Type":"multipart/form-data; boundary="+boundary})
    with urllib.request.urlopen(req,timeout=30) as response:
        assert response.status==201
        preview=json.loads(response.read())["data"]
    assert preview["error_count"]==0
    return envelope(f"/quality-data/imports/{preview['id']}/confirm",token=token,body={})


def main():
    credentials = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
    account = next(item for item in credentials["accounts"] if item["username"] == "demo_analyst")
    session = envelope("/auth/token", org=credentials["organization"], body={"username":account["username"],"password":account["password"]})
    token = session["access_token"]
    case_id = str(uuid5(NAMESPACE_URL, "piap-quality-demo:case"))
    workspace = envelope(f"/risk-cases/{case_id}/workspace", token=token)
    contexts = [envelope(f"/quality-data/records/{row['id']}/context", token=token) for row in workspace["records"]]
    baseline = next(item for item in contexts if item["record"]["external_record_id"] == "DEMO-QS-001-01")
    objects = baseline["objects"]
    refs = envelope("/quality-data/reference-options", token=token)
    assert any(item["id"]==objects["enterprise"]["id"] for item in refs["enterprises"])
    assert all(set(item)=={"id","name"} for item in refs["enterprises"])
    for context in contexts:
        if context["record"]["external_record_id"] in {"DEMO-QS-001-01","DEMO-QS-001-02","DEMO-QS-001-03"}:
            assert context["objects"]["enterprise"]["id"] == objects["enterprise"]["id"]
            assert context["objects"]["product"]["id"] == objects["product"]["id"]
            assert any(item["id"]==case_id for item in context["related_cases"])
    existing = next(attachment for item in contexts for attachment in item["attachments"])
    status, content = request(f"/quality-data/attachments/{existing['id']}/download", token=token)
    assert status == 200
    first = upload(token, existing["file_name"], content)
    second = upload(token, existing["file_name"], content)
    assert first["id"] == second["id"] == existing["id"]
    payload = {"external_record_id":"DEMO-QS-001-P2-UNKNOWN","origin_label":"阶段二隔离验收",
        "record_type":"consumer_complaint","occurred_at":None,"content":{"text":"【演示】阶段二对象核对验收资料","product_description":"原资料未核对型号"},
        "enterprise_ref":{"name":"原资料称某厂"},"attachment_ids":[first["id"]]}
    status, body = request("/quality-data/events",token=token,body=payload)
    assert status == 201
    original = body["data"]
    context = envelope(f"/quality-data/records/{original['id']}/context",token=token)
    version = int(original["provenance"].get("object_binding_version",0))
    if not version:
        assert all(item["status"]=="unlinked" for item in context["objects"].values())
    assert original["occurred_at"] is None
    status, duplicate = request("/quality-data/events", token=token, body=payload)
    assert status == 201 and duplicate["data"]["duplicate"] and duplicate["data"]["id"] == original["id"]
    imported = import_existing(token, payload)
    assert imported["created_count"]==0 and imported["duplicate_count"]==1
    assert imported["records"][0]["record_id"]==original["id"]
    patch = {"expected_version":version,"reason":"依据演示原件核对企业与产品档案",
        "enterprise_id":objects["enterprise"]["id"],"product_id":objects["product"]["id"],"category_id":objects["category"]["id"]}
    updated = envelope(f"/quality-data/records/{original['id']}/objects",token=token,body=patch,method="PATCH")
    for key in ["id","content_hash","content","occurred_at","received_at","attachment_ids"]:
        assert updated[key] == original[key]
    version = int(updated["provenance"]["object_binding_version"])
    stale = {**patch,"expected_version":version-1}
    assert request(f"/quality-data/records/{original['id']}/objects",token=token,body=stale,method="PATCH")[0] == 409
    no_change = envelope(f"/quality-data/records/{original['id']}/objects",token=token,body={**patch,"expected_version":version},method="PATCH")
    assert no_change["provenance"]["object_binding_version"] == version
    envelope(f"/risk-cases/{case_id}/sources",token=token,body={"source_record_ids":[original["id"]]})
    context = envelope(f"/quality-data/records/{original['id']}/context",token=token)
    assert context["objects"]["enterprise"]["status"]=="linked"
    assert any(item["id"]==case_id for item in context["related_cases"])
    assert context["record"]["enterprise_ref"]["name"] == "原资料称某厂"
    filtered = envelope(f"/quality-data/records?product_id={objects['product']['id']}&enterprise_id={objects['enterprise']['id']}&size=100",token=token)
    assert {item["id"] for item in workspace["records"]} | {original["id"]} <= {item["id"] for item in filtered["items"]}
    final = envelope(f"/risk-cases/{case_id}/workspace",token=token)
    assert sum(row["id"]==original["id"] for row in final["records"]) == 1
    assert not envelope("/quality-supervision/sampling-candidates",token=token)["items"]
    result = {"stage":2,"passed":True,"api_mode":"real_local_demo_server","source_record_id":original["id"],
        "scenario_case_id":case_id,"canonical_objects_shared":True,"original_content_preserved":True,"unknown_time_preserved":True,
        "upload_deduplicated":True,"submission_deduplicated":True,"cross_transport_reuse_verified":True,"binding_version":version,"stale_binding_rejected":True,
        "risk_sources":len(final["records"]),"formal_risk_confirmation":False,"remote_server_modified":False}
    (RUNTIME/"phase2-api-acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
