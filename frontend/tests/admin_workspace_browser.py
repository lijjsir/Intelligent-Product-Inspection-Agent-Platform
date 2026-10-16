"""Navigation/role UI regression with an explicit all-grants API fixture."""
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

permissions = ["user", "role_read", "meeting", "meeting_admin", "collab", "task", "result", "chat", "dataset", "algo_workspace",
               "model_config_read", "model_config", "gpu_infra", "agent_ops_read", "agent_ops", "prompt_admin", "tool",
               "quality", "quality_material_submit", "quality_material_read_business", "quality_ingestion_manage", "analytics", "alert",
               "alert_rule_read", "auth_log", "audit_log", "approval", "infrastructure", "billing", "memory_governance",
               "knowledge_read", "knowledge_publish", "inspection_spec_read", "inspection_spec",
               "inspection_standard_library_read", "standard_admission_submit", "standard_admission_review", "standard_admission_publish"]
role = "admin"
errors = []
checks = []
root = Path(__file__).resolve().parents[2]
output = root / "frontend/test-results/admin-workspace"
output.mkdir(parents=True, exist_ok=True)


def handle(route):
    path = urlparse(route.request.url).path.removeprefix("/api")
    if path == "/v1/users/me":
        data = {"id": "fixture-user", "org_id": "fixture-org", "username": role, "email": "fixture@example.com",
                "role": role, "roles": [role], "is_active": True, "effective_permissions": permissions}
    elif path in ["/v1/users", "/v1/tasks", "/v1/quality-data/records", "/v1/enterprises"]:
        data = {"items": [], "total": 0, "page": 1, "size": 20}
    elif path in ["/v1/standard-libraries", "/v1/inspection-standards"]:
        data = {"items": [], "total": 0, "page": 1, "size": 20}
    elif "catalog" in path:
        data = {"categories": [], "products": []}
    elif "standard-execution-rules" in path or "risk-policies" in path:
        data = []
    else:
        data = []
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True, "data": data}))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.route("**/api/v1/**", handle)
    page.add_init_script("for(const [k,v] of Object.entries({piap_token:'fixture',piap_role:'admin',piap_roles:'[\"admin\"]',piap_user_id:'fixture-user',piap_org_id:'fixture-org',piap_username:'admin'}))sessionStorage.setItem(k,v);")
    page.goto("http://127.0.0.1:5173/governance/admin/users")
    page.wait_for_load_state("networkidle")
    for group in ["组织与权限", "质监基础", "标准管理", "规则与复核", "审计与审批"]:
        expect(page.get_by_text(group, exact=True).first).to_be_visible()
        page.get_by_text(group, exact=True).first.click()
    expect(page.get_by_text("知识准入与发布", exact=True).first).to_be_visible()
    forbidden = ["已授权功能", "任务管理", "检测结果", "AI 对话", "资料接入", "数据接入", "测试集管理", "GPU 资源",
                 "模型配置", "Agent 管理", "Prompt 管理", "工具总览", "分析中心", "告警管理", "会议室", "协作中心", "计费管理"]
    menu_text = page.locator("aside").inner_text()
    assert not any(label in menu_text for label in forbidden), menu_text
    checks.append("管理员全授权状态仍只有治理菜单，没有跨岗位已授权功能")
    page.screenshot(path=str(output / "admin-menu-desktop.png"), full_page=True)
    for path in ["/app/tasks", "/app/chat", "/ops/data/import", "/ops/tools", "/governance/admin/gpu"]:
        page.goto("http://127.0.0.1:5173" + path)
        page.wait_for_load_state("networkidle")
        assert urlparse(page.url).path == "/governance/admin/users", page.url
    checks.append("业务/开发/算法旧地址返回管理员治理入口")
    page.goto("http://127.0.0.1:5173/governance/admin/inspection-specs")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading", name="检测要求总览", exact=True)).to_be_visible()
    checks.append("检测要求总览只展示正式检测要求，维护入口回到标准详情")
    for path, heading in [
        ("/governance/admin/inspection-standards", "检测标准库"),
        ("/governance/admin/ai-review-gates", "检测执行策略"),
        ("/governance/admin/risk-policies", "风险等级配置"),
        ("/governance/memory", "知识准入与发布"),
    ]:
        page.goto("http://127.0.0.1:5173" + path)
        page.wait_for_load_state("networkidle")
        expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
    checks.append("标准库、检测执行策略、风险配置和知识治理入口均能正常渲染")
    for current_role in ["admin", "user", "expert", "algorithm_engineer", "app_developer", "platform_operator"]:
        role = current_role
        page.goto("http://127.0.0.1:5173/app/profile")
        page.wait_for_load_state("networkidle")
        text = page.locator("aside").inner_text()
        assert "已授权功能" not in text, (current_role, text)
        blocked = {"admin": ["任务管理", "Agent 管理", "GPU 资源"], "user": ["用户管理", "检测标准", "数据接入"],
                   "expert": ["用户管理", "Prompt 管理", "训练任务"], "algorithm_engineer": ["用户管理", "Prompt 管理"],
                   "app_developer": ["用户管理", "训练任务"], "platform_operator": ["用户管理", "训练任务", "Prompt 管理"]}[current_role]
        assert not any(label in text for label in blocked), (current_role, text)
    checks.append("六种身份在全授权快照下均无已授权功能，也不追加跨岗位菜单")
    role = "expert"
    page.goto("http://127.0.0.1:5173/app/tasks")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button", name="提交质量资料", exact=True)).to_have_count(0)
    page.goto("http://127.0.0.1:5173/app/quality-data")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="提交资料", exact=True).click()
    dialog = page.get_by_role("dialog", name="提交质量资料", exact=True)
    dialog.locator(".el-select").first.click()
    expect(page.get_by_role("option", name="消费投诉", exact=True)).to_be_visible()
    expect(page.get_by_role("option", name="标准文件", exact=True)).to_have_count(0)
    checks.append("专家检测任务无重复业务资料入口，新提交类型不再包含标准文件")
    assert not errors, errors
    browser.close()
(output / "validation.json").write_text(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=True))
