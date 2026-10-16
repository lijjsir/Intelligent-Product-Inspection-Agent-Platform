"""Browser acceptance for the inspection execution workflow using API fixtures."""

import copy
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:5173"
OUTPUT = Path(__file__).resolve().parents[1] / "test-results" / "inspection-execution"
OUTPUT.mkdir(parents=True, exist_ok=True)

permissions = [
    "task",
    "result",
    "inspection_execution",
    "inspection_execution_review",
    "quality",
]


def envelope(data):
    return {"success": True, "code": "ok", "message": "ok", "data": data}


def run_fixture(status="draft"):
    return {
        "id": "run-fixture-1",
        "task_id": "task-fixture-1",
        "row_version": 1 if status == "draft" else 2,
        "status": status,
        "effective_status": status,
        "created_by": "user-fixture-1",
        "reviewed_by": "expert-fixture-1" if status == "accepted" else None,
        "current_source_issues": [],
        "snapshot": {
            "sample_ids": ["SAMPLE-001"],
            "observations": [
                {
                    "kind": "measurement_record",
                    "id": "measurement-001",
                    "measurement_key": "thermal_shock_water_bath_temperature",
                    "sample_id": "SAMPLE-001",
                    "value": 20,
                    "unit": "℃",
                    "method": "校准温度计",
                    "conditions": {"temperature_c": 20, "tolerance_c": 2},
                }
            ],
            "rules": [
                {
                    "standard_no": "GB/T 3298-2022",
                    "clause_no": "6.2",
                    "indicator": "流动水槽水温",
                    "operator": "between",
                    "lower": 18,
                    "upper": 22,
                    "unit": "℃",
                }
            ],
            "source_refs": [
                {
                    "standard_no": "GB/T 3298-2022",
                    "clause_no": "6.2",
                    "page_number": 5,
                    "source_text": "流动水槽可保持温度在20 ℃±2 ℃的流动水。",
                }
            ],
            "policy": {"version": "2026.10", "status": "published"},
        },
        "evaluation": {
            "item_verdict": "pass",
            "product_verdict": "not_assessed",
            "checks": [
                {
                    "sample_id": "SAMPLE-001",
                    "standard_no": "GB/T 3298-2022",
                    "clause_no": "6.2",
                    "indicator": "流动水槽水温",
                    "unit": "℃",
                    "status": "pass",
                    "findings": [{"evidence_id": "measurement-001", "value": 20}],
                }
            ],
            "missing_inputs": [],
            "review_reasons": [],
            "boundary": "本记录只判定选定的标准项目，不代表整份标准或产品整体合格。",
            "risk_level": "unknown",
            "consumed_evidence_ids": ["measurement-001"],
        },
        "created_at": "2026-10-06T10:00:00+08:00",
    }


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1050})
    page = context.new_page()
    actions = []
    errors = []
    state = {"run": None}
    session = {
        "piap_token": "fixture-token",
        "piap_role": "expert",
        "piap_roles": json.dumps(["expert"]),
        "piap_user_id": "expert-fixture-1",
        "piap_org_id": "fixture-org",
        "piap_username": "fixture-expert",
    }
    page.add_init_script(
        "for (const [key, value] of Object.entries(%s)) sessionStorage.setItem(key, value);"
        % json.dumps(session)
    )
    page.on("pageerror", lambda error: errors.append(str(error)))

    task = {
        "id": "task-fixture-1",
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
    requirement = {
        "id": "candidate-fixture-1",
        "revision_id": "revision-fixture-1",
        "standard_no": "GB/T 3298-2022",
        "clause_no": "6.2",
        "indicator": "流动水槽水温",
        "method": "温度计测量",
        "conditions": "20 ℃±2 ℃",
        "unit": "℃",
        "requirement": "18 ℃ ~ 22 ℃",
        "operator": "between",
        "measurement_key": "thermal_shock_water_bath_temperature",
        "status": "confirmed",
    }

    def handle(route):
        request = route.request
        path = urlparse(request.url).path.removeprefix("/api")
        method = request.method
        if method not in {"GET", "HEAD", "OPTIONS"}:
            actions.append({"method": method, "path": path, "body": request.post_data_json})

        if path == "/v1/users/me":
            data = {
                "id": "expert-fixture-1",
                "org_id": "fixture-org",
                "username": "fixture-expert",
                "email": "expert@example.com",
                "role": "expert",
                "roles": ["expert"],
                "is_active": True,
                "effective_permissions": permissions,
            }
        elif path == "/v1/tasks/task-fixture-1":
            data = task
        elif path == "/v1/tasks/task-fixture-1/events":
            data = [{"id": "event-1", "type": "completed", "status": "done", "message": "任务完成"}]
        elif path == "/v1/inspection-execution/requirements":
            assert parse_qs(urlparse(request.url).query).get("task_id") == ["task-fixture-1"]
            data = [requirement]
        elif path == "/v1/inspection-execution/runs" and method == "GET":
            data = [state["run"]] if state["run"] else []
        elif path == "/v1/inspection-execution/runs" and method == "POST":
            state["run"] = run_fixture()
            data = state["run"]
        elif path == "/v1/inspection-execution/runs/run-fixture-1" and method == "GET":
            data = state["run"] or run_fixture()
        elif path == "/v1/inspection-execution/runs/run-fixture-1/review" and method == "POST":
            state["run"] = run_fixture("accepted")
            data = state["run"]
        elif path == "/v1/streams/session" and method == "POST":
            data = {"stream_token": "fixture-stream-token", "resource": "task", "resource_id": task["id"]}
        else:
            data = []
        route.fulfill(status=200, content_type="application/json", body=json.dumps(envelope(data), ensure_ascii=False))

    page.route("**/api/v1/**", handle)
    page.goto(f"{BASE}/app/tasks/{task['id']}")
    page.wait_for_load_state("networkidle")

    expect(page.get_by_role("heading", name="标准要求执行与独立复核", exact=True)).to_be_visible()
    expect(page.get_by_text("本任务还没有标准执行记录", exact=True)).to_be_visible()
    page.screenshot(path=str(OUTPUT / "01-task-detail-empty.png"), full_page=True)

    page.get_by_role("button", name="新建执行记录", exact=True).click()
    dialog = page.get_by_role("dialog", name="新建标准执行记录")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_text("常用试验条件", exact=True)).to_be_visible()
    requirement_option = dialog.locator(".requirement-option").filter(has_text="流动水槽水温")
    requirement_option.locator("input[type='checkbox']").evaluate("element => element.click()")

    def field(label):
        return dialog.locator(".el-form-item").filter(has_text=re.compile(r"^\s*" + re.escape(label))).locator("input, textarea").first

    field("产品类别").fill("陶瓷日用器具")
    dialog.locator(".el-form-item").filter(has_text="实际生产日期").locator("input").fill("2026-10-06")
    field("样品编号（每行一条）").fill("SAMPLE-001")
    field("来源编号").fill("measurement-001")
    field("测量项目 / 字段").fill("thermal_shock_water_bath_temperature")
    sample_select = dialog.locator(".evidence-card").locator(".el-form-item").filter(has_text="样品编号").locator(".el-select")
    sample_select.click()
    page.get_by_role("option", name="SAMPLE-001", exact=True).click()
    dialog.locator(".evidence-card").locator(".el-form-item").filter(has_text="实测值 / 报告值").locator("input").fill("20")
    dialog.locator(".evidence-card").locator(".el-form-item").filter(has_text="单位").locator("input").fill("℃")
    dialog.locator(".evidence-card").locator(".el-form-item").filter(has_text="方法").locator("input").fill("校准温度计")
    dialog.get_by_role("button", name="保存证据并执行", exact=True).click()

    expect(dialog).not_to_be_visible()
    drawer = page.get_by_role("dialog", name="标准执行结果与证据")
    expect(drawer.get_by_role("heading", name="选定项目符合要求", exact=True)).to_be_visible()
    expect(drawer.get_by_text("GB/T 3298-2022", exact=True)).to_be_visible()
    expect(page.get_by_text("来源可追溯", exact=True)).to_be_visible()
    expect(drawer.get_by_text("本记录只判定选定的标准项目", exact=False)).to_be_visible()
    page.screenshot(path=str(OUTPUT / "02-execution-result.png"), full_page=True)

    drawer.get_by_role("button", name="独立专业复核", exact=True).click()
    review = page.get_by_role("dialog", name="独立专业复核")
    expect(review).to_be_visible()
    review.locator(".el-form-item").filter(has_text="复核说明").locator("textarea").fill("已核对温度实测记录、标准条款和来源页码")
    review.get_by_role("button", name="确认并记录", exact=True).click()
    expect(review).not_to_be_visible()
    expect(drawer.get_by_text("专家已确认", exact=True)).to_be_visible()
    expect(drawer.get_by_role("button", name="独立专业复核", exact=True)).to_have_count(0)
    page.screenshot(path=str(OUTPUT / "03-execution-accepted.png"), full_page=True)

    execution_actions = [item for item in actions if item["path"].startswith("/v1/inspection-execution/")]
    assert [item["path"] for item in execution_actions] == [
        "/v1/inspection-execution/runs",
        "/v1/inspection-execution/runs/run-fixture-1/review",
    ], actions
    assert execution_actions[0]["body"]["requirements"][0]["candidate_id"] == requirement["id"]
    assert execution_actions[0]["body"]["observations"][0]["value"] == 20
    assert execution_actions[1]["body"]["decision"] == "accept"
    assert not errors, errors
    report = {"checks": ["任务选择标准要求", "登记实测证据", "显示规则判定与来源", "专家独立复核"], "actions": actions, "page_errors": errors}
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    context.close()
    browser.close()
