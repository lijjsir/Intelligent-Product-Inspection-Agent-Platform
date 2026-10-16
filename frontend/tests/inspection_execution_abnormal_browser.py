"""Browser acceptance for non-happy-path inspection execution states."""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:5173"
OUTPUT = Path(__file__).resolve().parents[1] / "test-results" / "inspection-execution"
OUTPUT.mkdir(parents=True, exist_ok=True)


def envelope(data):
    return {"success": True, "code": "ok", "message": "ok", "data": data}


def run_fixture(run_id, verdict, *, status="draft", source_issues=None, check_status=None):
    check_status = check_status or verdict
    missing = [] if check_status in {"pass", "fail"} else ["缺少有效测量记录，或试验条件尚未核对"]
    finding = {"evidence_id": f"evidence-{run_id}", "value": 26 if check_status == "fail" else 20}
    check = {
        "sample_id": "SAMPLE-001",
        "standard_no": "GB/T 3298-2022",
        "clause_no": "6.2",
        "indicator": "流动水槽水温",
        "unit": "℃",
        "status": check_status,
        "findings": [] if check_status in {"incomplete", "uncertain", "manual_required"} else [finding],
        "missing_inputs": missing,
    }
    return {
        "id": run_id,
        "task_id": "task-fixture-abnormal",
        "row_version": 2 if status != "draft" else 1,
        "status": status,
        "effective_status": "needs_reassessment" if source_issues else status,
        "created_by": "user-fixture-1",
        "reviewed_by": "expert-fixture-1" if status == "accepted" else None,
        "current_source_issues": source_issues or [],
        "snapshot": {"sample_ids": ["SAMPLE-001"], "observations": [], "rules": [], "source_refs": [], "policy": {}},
        "evaluation": {
            "item_verdict": verdict,
            "product_verdict": "not_assessed",
            "checks": [check],
            "missing_inputs": missing,
            "review_reasons": ["选定项目结论需独立专业复核"],
            "boundary": "本记录只判定选定的标准项目，不代表整份标准或产品整体合格。",
            "risk_level": "unknown",
            "consumed_evidence_ids": [] if not finding else [finding["evidence_id"]],
        },
        "created_at": "2026-10-06T10:00:00+08:00",
    }


task = {
    "id": "task-fixture-abnormal",
    "org_id": "fixture-org",
    "product_id": "product-fixture-1",
    "product_name": "陶瓷试样",
    "product_line_name": "陶瓷日用器具",
    "product_sku_code": "CER-001",
    "spec_code": "GB/T 3298-2022",
    "standard_name": "陶瓷烹调器",
    "batch_no": "BATCH-001",
    "status": "done",
    "priority": 2,
    "has_result": False,
    "has_stability": False,
    "source_kind": "task_list",
    "created_at": "2026-10-06T09:00:00+08:00",
}
runs = [
    run_fixture("run-incomplete", "incomplete", check_status="uncertain"),
    run_fixture("run-fail", "fail", check_status="fail"),
    run_fixture("run-withdrawn", "pass", status="accepted", source_issues=["标准来源已撤回，历史快照保留供核对"]),
]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1050})
    page = context.new_page()
    errors = []
    session = {
        "piap_token": "fixture-token",
        "piap_role": "expert",
        "piap_roles": json.dumps(["expert"]),
        "piap_user_id": "expert-fixture-1",
        "piap_org_id": "fixture-org",
        "piap_username": "fixture-expert",
    }
    page.add_init_script("for (const [key, value] of Object.entries(%s)) sessionStorage.setItem(key, value);" % json.dumps(session))
    page.on("pageerror", lambda error: errors.append(str(error)))

    def handle(route):
        request = route.request
        path = urlparse(request.url).path.removeprefix("/api")
        if path == "/v1/users/me":
            data = {"id": "expert-fixture-1", "org_id": "fixture-org", "username": "fixture-expert", "email": "expert@example.com", "role": "expert", "roles": ["expert"], "is_active": True, "effective_permissions": ["task", "result", "inspection_execution", "inspection_execution_review", "quality"]}
        elif path == f"/v1/tasks/{task['id']}":
            data = task
        elif path == f"/v1/tasks/{task['id']}/events":
            data = []
        elif path == "/v1/inspection-execution/runs" and request.method == "GET":
            data = runs
        elif path.startswith("/v1/inspection-execution/runs/") and request.method == "GET":
            run_id = path.rsplit("/", 1)[-1]
            data = next(run for run in runs if run["id"] == run_id)
        elif path == "/v1/streams/session" and request.method == "POST":
            data = {"stream_token": "fixture-stream-token", "resource": "task", "resource_id": task["id"]}
        else:
            data = []
        route.fulfill(status=200, content_type="application/json", body=json.dumps(envelope(data), ensure_ascii=False))

    page.route("**/api/v1/**", handle)
    page.goto(f"{BASE}/app/tasks/{task['id']}")
    page.wait_for_load_state("networkidle")

    rows = page.locator(".execution-panel .el-table__body-wrapper tbody tr")
    expect(rows).to_have_count(3)
    rows.nth(0).get_by_role("button", name="查看执行详情").click()
    drawer = page.get_by_role("dialog", name="标准执行结果与证据")
    expect(drawer.get_by_role("heading", name="检测或依据尚不完整", exact=True)).to_be_visible()
    expect(drawer.get_by_text("当前结果不能直接确认", exact=True)).to_be_visible()
    drawer.get_by_role("button", name="处理复核意见", exact=True).click()
    review = page.get_by_role("dialog", name="独立专业复核")
    expect(review).to_be_visible()
    expect(review.get_by_text("当前存在缺失证据、来源问题或未确定项目，只能先补证或驳回。", exact=True)).to_be_visible()
    expect(review.locator(".el-select-dropdown")).to_have_count(0)
    review.get_by_role("button", name="取消", exact=True).click()
    drawer.locator(".el-drawer__close-btn").click()

    rows.nth(1).get_by_role("button", name="查看执行详情").click()
    drawer = page.get_by_role("dialog", name="标准执行结果与证据")
    expect(drawer.get_by_role("heading", name="存在不符合项目", exact=True)).to_be_visible()
    expect(drawer.get_by_text("不符合", exact=True).first).to_be_visible()
    drawer.locator(".el-drawer__close-btn").click()

    rows.nth(2).get_by_role("button", name="查看执行详情").click()
    drawer = page.get_by_role("dialog", name="标准执行结果与证据")
    page.wait_for_timeout(500)
    expect(drawer.get_by_role("heading", name="选定项目符合要求", exact=True)).to_be_visible()
    expect(drawer.get_by_text("需重新评估", exact=True).first).to_be_visible()
    expect(drawer.get_by_text("标准来源已撤回，历史快照保留供核对", exact=True)).to_be_visible()
    page.screenshot(path=str(OUTPUT / "04-abnormal-execution-states.png"), full_page=True)

    assert not errors, errors
    print(json.dumps({"checks": ["不完整证据不可直接确认", "超限结果显示不符合", "来源失效显示需重新评估"], "page_errors": errors}, ensure_ascii=False))
    context.close()
    browser.close()
