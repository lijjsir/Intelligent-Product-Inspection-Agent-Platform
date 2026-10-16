"""Live read-only candidate checks and browser fixtures for current risk context controls."""
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:5173"
OUT = ROOT / "frontend/test-results/risk-sampling-context"
OUT.mkdir(parents=True, exist_ok=True)
inventory = json.loads((ROOT / "backend/runtime/industrial_case_20261014/runtime_inventory.json").read_text(encoding="utf-8"))
actor = next(u for u in inventory["users"] if u["username"] == "expert")
code = "from app.core.security import create_access_token; print(create_access_token(" + repr(actor["id"]) + ", " + repr({"org_id": inventory["org_id"], "role": "expert"}) + "))"
token = subprocess.run(["docker", "exec", "piap-backend", "python", "-c", code], capture_output=True, check=True).stdout.decode().strip()
checks, errors, unexpected_http = [], [], []
state = {"market_failure": False, "replacement": False, "isolated_posts": 0}
case_id = "10000000-0000-4000-8000-000000000001"
plan_id = "10000000-0000-4000-8000-000000000002"
draft_id = "10000000-0000-4000-8000-000000000003"
ref = {"kind": "quality_risk_case", "case_id": case_id, "assessment_id": "10000000-0000-4000-8000-000000000004", "version": 3, "source_hash": "isolated"}
plan = {"id": plan_id, "org_id": inventory["org_id"], "kind": "sampling-plans", "code": "ISOLATED-PLAN",
    "name": "隔离抽查方案", "status": "approved", "version": 4, "created_by": actor["id"],
    "created_at": "2026-10-14T00:00:00Z", "updated_at": "2026-10-14T00:00:00Z",
    "data": {"risk_refs": [ref], "candidates": [{"case_id": case_id, "sample_count": 2, "unit_cost": 10}],
        "budget": 100, "max_samples": 3, "max_staff_hours": 3, "hours_per_sample": 1, "required_categories": [],
        "analysis": {"status": "completed", "selected": [{"case_id": case_id, "sample_count": 2}]},
        "review_decisions": [], "knowledge_status": "current"}}
draft = {**plan, "id": draft_id, "code": "ISOLATED-REASSESSMENT", "status": "draft", "version": 2,
    "data": {**{k: v for k, v in plan["data"].items() if k not in {"analysis", "review_decisions", "knowledge_status"}},
        "reassessment_basis": {"source_id": plan_id, "source_code": plan["code"], "source_version": 4,
            "feedback": [{"text": "隔离回访反馈：核对追加证据"}]}}}
report = {"summary": "隔离风险来源核验", "dimensions": {}, "confirmed_categories": [], "plans": [], "sessions": [],
    "metric_status": "隔离数据未作业务验收", "limitations": ["隔离浏览器响应"],
    "excluded_count": 2, "legacy_unverified_count": 1, "unknown_time_count": 3}


def reply(route, data, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps({"success": status == 200,
        "code": "ok" if status == 200 else "unavailable", "message": "" if status == 200 else "隔离市场查询未能加载", "data": data}))


def guard(route):
    request = route.request
    path = urlparse(request.url).path
    if path == "/api/v1/chat/sessions" or path.endswith("/events"):
        reply(route, []); return
    if path == "/api/v1/collab/summary":
        reply(route, {"pending_count": 0, "initiated_count": 0, "processed_count": 0}); return
    if path == "/api/v1/streams/session":
        body = request.post_data_json
        reply(route, {"stream_token": "isolated-browser", "expires_at": "2027-01-01T00:00:00Z", "resource": body["resource"], "resource_id": body["resource_id"]}); return
    if path.endswith("/stream"):
        route.fulfill(status=200, content_type="text/event-stream", body=": isolated\n\n"); return
    if path == f"/api/v1/sampling-plans/{plan_id}/reassessment":
        assert request.method == "POST"
        state["replacement"] = True
        state["isolated_posts"] += 1
        reply(route, draft); return
    assert request.method == "GET", "No live business writes are allowed"
    if path == "/api/v1/quality-supervision/analytics":
        reply(route, None if state["market_failure"] else report, 503 if state["market_failure"] else 200); return
    if path == "/api/v1/quality-supervision/sampling-candidates":
        reply(route, {"items": [{"id": case_id, "code": "ISOLATED-RISK", "title": "隔离有效风险", "assessment_version": 3, "risk_level": "high"}], "excluded_count": 2}); return
    if path == "/api/v1/sampling-plans":
        rows = [draft, plan] if state["replacement"] else [plan]
        reply(route, {"items": rows, "total": len(rows), "page": 1, "size": 20}); return
    if path in {f"/api/v1/sampling-plans/{plan_id}", f"/api/v1/sampling-plans/{draft_id}"}:
        reply(route, draft if path.endswith(draft_id) else plan); return
    response = route.fetch()
    if response.status >= 400:
        unexpected_http.append({"path": path, "status": response.status})
    route.fulfill(response=response)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1100}, timezone_id="Asia/Shanghai")
    stored = {"piap_token": token, "piap_role": "expert", "piap_roles": '["expert"]',
        "piap_user_id": actor["id"], "piap_org_id": inventory["org_id"], "piap_username": "expert"}
    context.add_init_script("try{if(location.origin===" + json.dumps(BASE) + ")for(const[k,v]of Object.entries(" + json.dumps(stored) + "))sessionStorage.setItem(k,v);}catch(_){}")
    headers = {"Authorization": "Bearer " + token}
    response = context.request.get(BASE + "/api/v1/quality-supervision/sampling-candidates", headers=headers)
    assert response.status == 200 and not response.json()["data"]["items"]
    checks.append("Live pending risks are excluded from current sampling candidates")
    response = context.request.get(BASE + "/api/v1/quality-supervision/analytics", headers=headers)
    assert response.status == 200
    actual = response.json()["data"]
    assert all(key in actual for key in ["excluded_count", "unknown_time_count", "risk_refs"])
    checks.append("Live market API serves current risk validity metadata")
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/api/v1/**", guard)
    page.goto(BASE + "/app/quality-analytics", wait_until="networkidle")
    expect(page.get_by_text("3 条历史确认风险需重新核验，未计入当前态势。", exact=True)).to_be_visible()
    expect(page.get_by_text("3 条有效风险缺少发生时间，未计入周期变化。", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "market-validity.png"), full_page=True)
    state["market_failure"] = True
    page.get_by_role("button", name="刷新", exact=True).click()
    expect(page.get_by_role("button", name="重试", exact=True)).to_be_visible()
    state["market_failure"] = False
    page.get_by_role("button", name="重试", exact=True).click()
    expect(page.get_by_text("隔离风险来源核验", exact=True)).to_be_visible()
    checks.append("Market page separates excluded and unknown-time records and recovers from request failures")
    page.goto(BASE + f"/app/sampling-plans?record={plan_id}", wait_until="networkidle")
    expect(page.get_by_text("引用的风险研判", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="结果反馈", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="新建重评估方案", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "sampling-reviewed.png"), full_page=True)
    checks.append("Sampling details show frozen assessment version and feedback/reassessment actions")
    page.get_by_role("button", name="新建重评估方案", exact=True).click()
    expect(page.get_by_text("重评估来源与反馈", exact=True)).to_be_visible()
    expect(page.get_by_text("隔离回访反馈：核对追加证据", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "sampling-reassessment.png"), full_page=True)
    checks.append("Isolated reassessment creates a draft and displays retained original feedback")
    page.get_by_role("button", name="新增监督抽查", exact=True).click()
    dialog = page.get_by_role("dialog", name="新增监督抽查", exact=True)
    expect(dialog.get_by_text("2 条历史确认风险需重新核验，暂不能作为抽查候选。", exact=True)).to_be_visible()
    dialog.get_by_role("button", name="取消", exact=True).click()
    checks.append("Candidate form warns about excluded source-invalid risks")
    assert state["isolated_posts"] == 1 and not errors and not unexpected_http, (errors, unexpected_http)
    browser.close()
result = {"checks": checks, "page_errors": errors, "unexpected_http_errors": unexpected_http,
    "isolated_post_responses": state["isolated_posts"], "live_business_writes": 0}
(OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
