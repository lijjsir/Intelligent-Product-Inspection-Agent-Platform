"""P0 UI behavior against explicit API fixtures; never mutates live resources."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("PIAP_PERMISSION_BASE_URL", "http://127.0.0.1:5173")
OUTPUT = Path(__file__).resolve().parents[1] / "test-results" / "standard-knowledge-p0"
OUTPUT.mkdir(parents=True, exist_ok=True)
errors = []
mutations = []
checks = []
sys.stdout.reconfigure(encoding="utf-8")


def space(space_id, owner, name):
    return {"id": space_id, "org_id": "fixture-org", "created_by": owner, "name": name,
            "description": "P0 UI fixture", "status": "ready", "file_count": 1, "folder_count": 0,
            "chunk_count": 1, "index_status": "ready", "selected_count": 0}


def new_page(browser, role, permissions):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    user_id = "expert-1" if role == "expert" else "admin-1"
    session = {"piap_token": "fixture", "piap_role": role, "piap_roles": json.dumps([role]),
               "piap_user_id": user_id, "piap_org_id": "fixture-org", "piap_username": role}
    page.add_init_script("for(const [k,v] of Object.entries(" + json.dumps(session) + "))sessionStorage.setItem(k,v);")
    page.on("pageerror", lambda err: errors.append(str(err)))

    def handle(route):
        path = urlparse(route.request.url).path.removeprefix("/api")
        if route.request.method not in {"GET", "HEAD", "OPTIONS"}:
            mutations.append({"method": route.request.method, "path": path})
        if path == "/v1/users/me":
            data = {"id": user_id, "org_id": "fixture-org", "username": role, "email": "fixture@example.com",
                    "role": role, "roles": [role], "is_active": True, "effective_permissions": permissions}
        elif path == "/v1/rag-spaces":
            data = [space("system-space", None, "P0系统标准空间"), space("shared-space", "owner-2", "P0授权资料"), space("my-space", "expert-1", "P0我的资料")]
        elif path.endswith("/tree"):
            space_id = path.split("/")[-2]
            data = [{"id": f"{space_id}-file", "org_id": "fixture-org", "rag_space_id": space_id,
                     "node_type": "file", "name": "fixture.pdf", "full_path": "fixture.pdf", "depth": 0,
                     "status": "ready", "children_count": 0, "children": []}]
        elif path in {"/v1/users", "/v1/standard-libraries", "/v1/inspection-standards", "/v1/enterprises"}:
            data = {"items": [], "total": 0, "page": 1, "size": 20}
        elif "catalog" in path:
            data = {"categories": [], "products": []}
        else:
            data = []
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True, "data": data}))

    page.route("**/api/v1/**", handle)
    return context, page


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    admin_context, admin = new_page(browser, "admin", ["user", "inspection_spec_read", "inspection_spec",
                                                     "inspection_standard_library_read"])
    admin.goto(BASE + "/governance/admin/ai-review-gates")
    admin.wait_for_load_state("networkidle")
    admin.screenshot(path=str(OUTPUT / "admin-inspection-gates.png"), full_page=True)
    expect(admin.get_by_role("heading", name="检测执行策略", exact=True)).to_be_visible()
    expect(admin.locator("aside").get_by_text("检测执行策略", exact=True)).to_be_visible()
    checks.append("管理员检测执行策略页面与治理菜单可达")
    admin.get_by_role("tab", name="历史兼容配置（只读）", exact=True).click()
    expect(admin.get_by_role("heading", name="历史兼容配置", exact=True)).to_be_visible()
    for name in ["新增规则", "编辑", "复制", "删除"]:
        expect(admin.get_by_role("button", name=name, exact=True)).to_have_count(0)
    checks.append("历史质检门槛只读展示，不提供新增、编辑、复制或删除操作")
    admin.screenshot(path=str(OUTPUT / "admin-inspection-gates.png"), full_page=True)
    admin.goto(BASE + "/ops/tools")
    admin.wait_for_load_state("networkidle")
    assert urlparse(admin.url).path == "/governance/admin/users"
    checks.append("恢复门槛入口没有开放管理员技术工作区")
    admin_context.close()

    denied_context, denied = new_page(browser, "admin", ["user", "inspection_standard_library_read"])
    denied.goto(BASE + "/governance/admin/ai-review-gates")
    denied.wait_for_load_state("networkidle")
    assert urlparse(denied.url).path != "/governance/admin/ai-review-gates"
    expect(denied.locator("aside").get_by_text("检测执行策略", exact=True)).to_have_count(0)
    checks.append("未授予门槛查看权限时不显示或进入入口")
    denied_context.close()

    expert_context, expert = new_page(browser, "expert", ["chat", "quality", "knowledge_read"])
    expert.goto(BASE + "/app/rag-spaces")
    expert.wait_for_load_state("networkidle")
    expert.get_by_role("tab", name="授权共享资料", exact=True).click()
    expect(expert.get_by_text("已授权共享资料 · 只读", exact=True)).to_be_visible()
    for name in ["编辑空间", "删除空间", "新建文件夹", "上传到当前文件夹"]:
        expect(expert.get_by_role("button", name=name, exact=True)).to_have_count(0)
    expect(expert.locator(".rag-node-actions")).to_have_count(0)
    checks.append("专家授权共享资料可读且无无效写操作")
    expert.screenshot(path=str(OUTPUT / "expert-shared-readonly.png"), full_page=True)
    expert.get_by_role("tab", name="我的资料", exact=True).click()
    expert.locator(".el-select").first.click()
    expert.get_by_role("option", name="P0我的资料", exact=True).click()
    expert.wait_for_load_state("networkidle")
    for name in ["编辑空间", "删除空间", "新建文件夹", "上传到当前文件夹"]:
        expect(expert.get_by_role("button", name=name, exact=True)).to_be_visible()
    expect(expert.locator(".rag-node-actions")).to_have_count(1)
    checks.append("专家本人资料空间仍保留维护能力")
    expert_context.close()
    browser.close()

assert not errors, errors
assert not mutations, mutations
report = {"checks": checks, "page_errors": errors, "api_mutations": mutations,
          "mode": "API fixtures; no live resource writes"}
(OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
