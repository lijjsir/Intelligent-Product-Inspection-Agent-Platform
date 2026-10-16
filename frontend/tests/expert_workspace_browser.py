"""Verify expert chat, task/result navigation and review without requiring standard browsing."""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

requests = []
session = {"id": "expert-chat", "title": "专家问答", "title_source": "manual", "org_id": "org-1", "user_id": "expert-1"}
task = {"id": "task-1", "org_id": "org-1", "created_by": "another-user", "product_id": "P-001", "product_name": "待复核产品",
        "spec_code": "STD-001", "standard_name": "已发布标准", "status": "done", "has_result": True, "has_stability": False,
        "image_urls": [], "priority": 5, "created_at": "2026-10-03T08:00:00"}
result = {"id": "result-1", "org_id": "org-1", "task_id": "task-1", "verdict": "manual_required", "overall_score": .5,
          "defects": [], "reasoning_chain": {}, "rag_citations": [], "reviewed_by": None, "reviewed_at": None, "review_note": None}
messages = []
answer = "专家复核应核对检测依据、缺陷记录和证据，确认后在结果页提交人工判定。"


def handle(route):
    request = route.request
    parsed = urlparse(request.url)
    path = parsed.path.removeprefix("/api")
    requests.append((request.method, path))
    data = []
    if path == "/v1/users/me":
        # Explicitly omit standards-read grants: chat and tasks must still work.
        data = {"id": "expert-1", "org_id": "org-1", "username": "expert", "email": "expert@example.com", "role": "expert", "is_active": True,
                "effective_permissions": ["chat", "task", "result", "feedback", "report_generate", "report_read"]}
    elif path in {"/v1/inspection-specs", "/v1/standard-libraries"}:
        raise AssertionError("Chat and task creation must not require standard management access")
    elif path == "/v1/chat/sessions":
        data = session if request.method == "POST" else [session]
    elif path == "/v1/chat/sessions/expert-chat/messages":
        if request.method == "POST":
            question = {"id": "q-1", "session_id": "expert-chat", "seq_no": 1, "role": "user", "message_type": "text", "content": request.post_data_json["message"], "payload": {}}
            messages[:] = [question, {"id": "a-1", "session_id": "expert-chat", "seq_no": 2, "role": "assistant", "message_type": "file_answer", "content": answer, "payload": {"status": "success"}}]
            data = {"user_message": question, "assistant_message_id": "a-1", "workflow_run_id": "workflow-1"}
        else:
            data = messages
    elif path == "/v1/streams/session":
        data = {"stream_token": "test", "resource": "chat", "resource_id": "expert-chat", "expires_at": "2099-01-01T00:00:00"}
    elif path.endswith("/stream"):
        route.fulfill(status=200, content_type="text/event-stream", body='event: ready\ndata: {"type":"ready"}\n\n')
        return
    elif path == "/v1/tasks/meta/creation-options":
        data = {"standards": [{"id": "standard-1", "name": "已发布标准", "spec_code": "STD-001", "required_image_count": 1, "required_views": ["正面"], "is_active": True}]}
    elif path == "/v1/tasks":
        data = {"items": [task], "total": 1, "page": 1, "size": 20}
    elif path == "/v1/tasks/task-1":
        data = task
    elif path == "/v1/quality-products/options" or "catalog" in path:
        data = {"categories": [{"id": "category-1", "name": "产品类别"}], "products": [{"id": "product-1", "category_id": "category-1", "name": "待复核产品"}]}
    elif path == "/v1/results":
        data = {"items": [{**result, "product_id": "P-001", "created_at": task["created_at"]}], "total": 1, "page": 1, "size": 20}
    elif path == "/v1/results/by-task/task-1":
        data = result
    elif path == "/v1/results/result-1/review":
        assert request.method == "PATCH"
        payload = request.post_data_json
        assert payload["verdict"] == "pass"
        result.update(verdict="pass", reviewed_by="expert-1", reviewed_at="2026-10-03T08:10:00", review_note=payload.get("note", ""))
        data = result
    elif path == "/v1/exports":
        if request.method == "GET":
            assert parse_qs(parsed.query).get("task_id") == ["task-1"]
            data = {"items": [], "total": 0, "page": 1, "size": 20}
        else:
            assert request.post_data_json["config_json"]["task_id"] == "task-1"
            data = {"id": "report-1", "report_type": "single_task", "status": "pending"}
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"code": "ok", "data": data}, ensure_ascii=False))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1065})
    page.set_default_timeout(10000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/v1/**", handle)
    page.add_init_script("""for(const [key,value] of Object.entries({piap_token:'test',piap_role:'expert',piap_roles:'["expert"]',piap_user_id:'expert-1',piap_org_id:'org-1',piap_username:'expert'})) sessionStorage.setItem(key,value);""")
    base = os.environ.get("PIAP_PERMISSION_BASE_URL", "http://127.0.0.1:5176")
    page.goto(f"{base}/app/chat")
    page.wait_for_load_state("networkidle")
    assert not any(path == "/v1/inspection-specs" for _method, path in requests)
    page.locator(".composer textarea").fill("专家如何复核检测结果？")
    page.get_by_role("button", name="发送", exact=True).click()
    expect(page.get_by_text(answer, exact=False)).to_be_visible(timeout=20000)
    page.goto(f"{base}/app/tasks")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading", name="检测任务", exact=True)).to_be_visible()
    expect(page.locator(".app-sidebar").get_by_role("link", name="检测任务", exact=True)).to_be_visible()
    expect(page.locator(".app-sidebar").get_by_role("link", name="检测结果", exact=True)).to_be_visible()
    page.get_by_role("button", name="新建任务", exact=True).click()
    expect(page.get_by_role("dialog", name="新建通用检测任务")).to_be_visible()
    assert any(path == "/v1/tasks/meta/creation-options" for _method, path in requests)
    page.get_by_role("dialog", name="新建通用检测任务").get_by_role("button", name="取消", exact=True).click()
    page.get_by_role("button", name="查看结果", exact=True).click()
    expect(page.get_by_role("heading", name="检测结果与专家复核", exact=True)).to_be_visible()
    review = page.locator(".review-form")
    expect(review.get_by_role("button", name="提交人工判定", exact=True)).to_be_visible()
    expect(page.locator(".el-loading-mask:visible")).to_have_count(0)
    review.locator(".el-select").click()
    page.get_by_role("option", name="产品合格", exact=True).click()
    review.get_by_role("textbox").fill("已核对检测依据与图像证据")
    review.get_by_role("button", name="提交人工判定", exact=True).click()
    expect(page.get_by_text("已核对检测依据与图像证据", exact=False)).to_be_visible()
    page.get_by_role("button", name="下载检测报告", exact=True).click()
    expect(page.get_by_text("当前任务的检测报告", exact=True)).to_be_visible()
    expect(page.get_by_text("当前任务的导出记录", exact=True)).to_be_visible()
    page.get_by_role("button", name="生成报告", exact=True).click()
    assert any(method == "POST" and path == "/v1/exports" for method, path in requests)
    assert not errors, errors
    browser.close()
    print("PASS: expert chat without standard-read permission, task creation fallback, result navigation, expert review and current-task report")
