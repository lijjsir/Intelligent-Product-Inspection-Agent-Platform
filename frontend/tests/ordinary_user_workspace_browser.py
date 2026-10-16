"""Verify the ordinary-user task/result/report flow against Vite with an in-memory API."""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

task = {"id": "task-1", "org_id": "org-1", "created_by": "user-2", "product_id": "P-001",
        "product_name": "测试产品", "product_category_name": "产品类别", "spec_code": "STD-001",
        "standard_name": "已发布检测标准", "status": "done", "has_result": True, "has_stability": False,
        "image_urls": [], "priority": 5, "created_at": "2026-10-03T08:00:00", "source_kind": "task_list"}
report = {"id": "report-1", "report_name": "测试产品检测报告", "report_type": "single_task", "format": "pdf",
          "status": "success", "config_json": json.dumps({"task_id": "task-1"}), "created_at": "2026-10-03T08:01:00"}
requests = []
active_permissions = ["chat", "task", "result", "feedback", "report_generate", "report_read", "product_master_read", "inspection_standard_library_read"]
chat_session = {"id": "chat-1", "title": "聊天验证", "title_source": "manual", "user_id": "user-2", "org_id": "org-1", "created_at": "2026-10-03T08:00:00"}
chat_messages = []
chat_answer = "检测前请准备清晰原图、产品型号和关注的问题，具体图片数量及视角以已发布标准为准。"


def handle(route):
    request = route.request
    parsed = urlparse(request.url)
    path = parsed.path.removeprefix("/api")
    requests.append((request.method, path, parse_qs(parsed.query)))
    data = []
    if path == "/v1/users/me":
        data = {"id": "user-2", "org_id": "org-1", "username": "user2", "email": "user2@example.com", "role": "user", "is_active": True,
                "effective_permissions": active_permissions}
    elif path == "/v1/chat/sessions":
        data = chat_session if request.method == "POST" else [chat_session]
    elif path == "/v1/chat/sessions/chat-1/messages":
        if request.method == "POST":
            payload = request.post_data_json
            chat_messages[:] = [
                {"id": "question-1", "session_id": "chat-1", "seq_no": 1, "role": "user", "message_type": "text", "content": payload["message"], "payload": {}, "created_at": "2026-10-03T08:00:01"},
                {"id": "answer-1", "session_id": "chat-1", "seq_no": 2, "role": "assistant", "message_type": "file_answer", "content": chat_answer, "payload": {"status": "success"}, "created_at": "2026-10-03T08:00:02"},
            ]
            data = {"user_message": chat_messages[0], "assistant_message_id": "answer-1", "workflow_run_id": "flow-1"}
        else:
            data = chat_messages
    elif path == "/v1/streams/session":
        data = {"stream_token": "test-stream", "resource": "chat", "resource_id": "chat-1", "expires_at": "2099-01-01T00:00:00"}
    elif path == "/v1/chat/sessions/chat-1/stream":
        route.fulfill(status=200, content_type="text/event-stream", body='event: ready\ndata: {"type":"ready"}\n\n')
        return
    elif path == "/v1/tasks":
        data = {"items": [task], "total": 1, "page": 1, "size": 20}
    elif path == "/v1/tasks/task-1":
        data = task
    elif path == "/v1/tasks/meta/creation-options":
        data = {"standards": [{"id": "standard-1", "name": "已发布检测标准", "spec_code": "STD-001", "required_image_count": 1, "required_views": ["正面"], "is_active": True}]}
    elif path == "/v1/quality-products/options":
        data = {"categories": [{"id": "category-1", "name": "产品类别"}], "products": [{"id": "product-1", "category_id": "category-1", "name": "测试产品"}]}
    elif path == "/v1/results/by-task/task-1":
        data = {"id": "result-1", "task_id": "task-1", "verdict": "pass", "overall_score": .92, "defects": [], "reasoning_chain": {}, "latency_ms": 100, "rag_citations": []}
    elif path == "/v1/results":
        data = {"items": [{"id": "result-1", "task_id": "task-1", "product_id": "P-001", "verdict": "pass", "overall_score": .92, "created_at": task["created_at"]}], "total": 1, "page": 1, "size": 20}
    elif path == "/v1/exports" and request.method == "GET":
        assert parse_qs(parsed.query).get("task_id") == ["task-1"]
        data = {"items": [report], "total": 1, "page": 1, "size": 20}
    elif path == "/v1/exports" and request.method == "POST":
        payload = request.post_data_json
        assert payload["report_type"] == "single_task"
        assert payload["config_json"]["task_id"] == "task-1"
        data = report
    elif path == "/v1/exports/report-1/download":
        route.fulfill(status=200, content_type="application/pdf", body=b"%PDF-1.4\nTest report fixture\n%%EOF")
        return
    elif path == "/v1/quality-products/catalog":
        raise AssertionError("Ordinary users must not browse the product directory")
    elif path.startswith(("/v1/standard-libraries", "/v1/inspection-specs")):
        raise AssertionError("Ordinary-user UI must not request the full standards browser")
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"code": "ok", "data": data}, ensure_ascii=False))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1065}, accept_downloads=True)
    page.set_default_timeout(10000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/v1/**", handle)
    page.add_init_script("""for(const [key,value] of Object.entries({piap_token:'test',piap_role:'user',piap_roles:'["user"]',piap_user_id:'user-2',piap_org_id:'org-1',piap_username:'user2'})) sessionStorage.setItem(key,value);""")
    base = os.environ.get("PIAP_PERMISSION_BASE_URL", "http://127.0.0.1:5176")
    page.goto(f"{base}/app/tasks")
    page.wait_for_load_state("networkidle")
    account = page.get_by_role("link", name="当前账号与个人设置")
    expect(account).to_contain_text("user2")
    expect(page.get_by_role("button", name="退出登录", exact=True)).to_be_visible()
    expect(page.locator(".app-sidebar").get_by_text("已授权功能", exact=True)).to_have_count(0)
    expect(page.locator(".app-sidebar").get_by_text("检测标准", exact=True)).to_have_count(0)
    expect(page.locator(".app-sidebar").get_by_role("link", name="检测结果", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="检测报告", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="导出报告", exact=True)).to_have_count(0)
    page.get_by_role("button", name="新建任务", exact=True).click()
    dialog = page.get_by_role("dialog", name="新建检测任务")
    expect(dialog).to_be_visible()
    assert any(path == "/v1/tasks/meta/creation-options" for _method, path, _query in requests)
    dialog.get_by_role("button", name="取消", exact=True).click()
    expect(dialog).to_be_hidden()
    output = Path(__file__).resolve().parents[1] / "test-results"
    output.mkdir(exist_ok=True)
    page.screenshot(path=str(output / "ordinary-user-tasks.png"), full_page=True)
    page.get_by_role("button", name="查看结果", exact=True).click()
    expect(page).to_have_url(f"{base}/app/results/task-1")
    expect(page.get_by_role("heading", name="检测结果", exact=True)).to_be_visible()
    page.get_by_role("button", name="下载检测报告", exact=True).click()
    expect(page.get_by_text("当前任务的检测报告", exact=True)).to_be_visible()
    expect(page.get_by_text("当前任务的导出记录", exact=True)).to_be_visible()
    page.get_by_role("button", name="生成报告", exact=True).click()
    with page.expect_download() as download:
        page.get_by_role("button", name="下载报告", exact=True).click()
    assert download.value.suggested_filename == "测试产品检测报告.pdf"
    expect(page.locator(".el-message")).to_have_count(0)
    page.screenshot(path=str(output / "ordinary-user-result-report.png"), full_page=True)
    page.goto(f"{base}/app/results")
    expect(page).to_have_url(f"{base}/app/results")
    expect(page.get_by_role("heading", name="我的检测结果", exact=True)).to_be_visible()
    expect(page.locator(".list-table").get_by_text("result-1", exact=True)).to_be_visible()
    page.screenshot(path=str(output / "ordinary-user-results.png"), full_page=True)
    page.goto(f"{base}/governance/admin/inspection-standards")
    expect(page).to_have_url(f"{base}/app/tasks")
    page.goto(f"{base}/app/export?task_id=task-1")
    expect(page).to_have_url(f"{base}/app/results/task-1?report=1")
    expect(page.get_by_text("当前任务的检测报告", exact=True)).to_be_visible()
    active_permissions.remove("report_generate")
    active_permissions.remove("feedback")
    page.reload()
    expect(page.get_by_text("当前任务的检测报告", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="生成报告", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="下载报告", exact=True)).to_be_visible()
    active_permissions.extend(["report_generate", "feedback"])
    page.goto(f"{base}/app/chat")
    page.wait_for_load_state("networkidle")
    page.locator(".composer textarea").fill("检测前需要准备哪些图片和资料？")
    page.get_by_role("button", name="发送", exact=True).click()
    expect(page.get_by_text(chat_answer, exact=False)).to_be_visible(timeout=20000)
    assert any(method == "POST" and path == "/v1/chat/sessions/chat-1/messages" for method, path, _query in requests)
    assert not any(path == "/v1/inspection-specs" for _method, path, _query in requests)
    expect(page.get_by_text("检测标准加载失败，请稍后重试。", exact=True)).to_have_count(0)
    page.screenshot(path=str(output / "ordinary-user-chat.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("link", name="当前账号与个人设置")).to_contain_text("user2")
    assert not errors, errors
    browser.close()
    print("PASS: username, focused task menu, creation options, result/report drawer, scoped history, generation/download, legacy redirects and mobile account display")
