"""Browser interaction checks with an in-memory API; run against Vite on :5173.

py -3.13 .agents/skills/webapp-testing/scripts/with_server.py --server
"cmd /c npm run dev -- --host 127.0.0.1 --port 5173" --port 5173 --
py -3.13 tests/permissions_matrix_browser.py
"""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

ROLE_ORDER = ["admin", "expert", "user", "algorithm_engineer", "app_developer", "platform_operator"]
ROLE_NAMES = {"admin": "管理员", "algorithm_engineer": "算法工程师", "user": "普通用户", "expert": "领域专家", "app_developer": "应用开发者", "platform_operator": "平台运营"}
CATALOG = [
    {"key": "feedback", "group": "inspection", "name": "异常反馈", "action": "使用"},
    {"key": "user", "group": "organization", "name": "用户管理", "action": "管理"},
    {"key": "dataset", "group": "algorithm", "name": "数据集", "action": "管理"},
    {"key": "algo_workspace", "group": "algorithm", "name": "算法工作台", "action": "使用"},
    {"key": "model_config_read", "group": "algorithm", "name": "模型配置", "action": "查看"},
    {"key": "model_config", "group": "algorithm", "name": "模型配置", "action": "管理"},
    {"key": "gpu_infra", "group": "algorithm", "name": "GPU 资源", "action": "管理"},
]
GROUPS = [{"key": key, "label": label} for key, label in [
    ("inspection", "检测与分析"), ("collaboration", "对话与协作"), ("algorithm", "算法与模型"),
    ("application", "应用与智能体"), ("knowledge", "标准与知识"), ("monitor", "监控与告警"),
    ("organization", "人员与权限"), ("governance", "系统治理"),
]]
resources = [action["key"] for action in CATALOG]
role_capabilities = {role: [] for role in ROLE_NAMES}
role_capabilities.update(admin=resources[:], algorithm_engineer=[key for key in resources if key != "user"], user=["feedback"], expert=["feedback"])
matrix = {role: role_capabilities[role][:] if role in {"admin", "algorithm_engineer"} else [] for role in ROLE_NAMES}
versions = {role: 0 for role in ROLE_NAMES}
users = [
    {"id": "engineer", "org_id": "org", "username": "张三", "role": "algorithm_engineer", "is_active": True},
    {"id": "ordinary", "org_id": "org", "username": "李四", "role": "user", "is_active": True},
    {"id": "admin", "org_id": "org", "username": "系统管理员", "role": "admin", "is_active": True},
]
for role in ROLE_ORDER[1:]:
    for index in range(1, 5):
        users.append({"id": f"{role}-{index}", "org_id": "org", "username": f"{role}{index}", "role": role, "is_active": True})
overrides = {user["id"]: {} for user in users}
user_versions = {user["id"]: 0 for user in users}


def matrix_data():
    return {"resources": resources, "matrix": matrix, "versions": versions, "catalog": CATALOG, "groups": GROUPS, "protected_roles": ["admin"], "role_capabilities": role_capabilities}


def user_data(user):
    denied = {key for key, effect in overrides[user["id"]].items() if effect == "deny"}
    granted = {key for key, effect in overrides[user["id"]].items() if effect == "grant"}
    return {"user_id": user["id"], "username": user["username"], "role": user["role"], "is_active": True,
            "role_default": matrix[user["role"]], "role_version": versions[user["role"]], "overrides": overrides[user["id"]],
            "effective": sorted((set(matrix[user["role"]]) | granted) - denied), "version": user_versions[user["id"]]}


def handle(route):
    url = urlparse(route.request.url)
    path = url.path.removeprefix("/api")
    method = route.request.method
    result = []
    if path == "/v1/users/me":
        result = {**users[2], "email": "admin@example.com", "effective_permissions": resources + ["role_read", "user", "organization", "collab", "meeting"]}
    elif path == "/v1/roles":
        result = [{"key": key, "label": label} for key in ROLE_ORDER for label in [ROLE_NAMES[key]]]
    elif path == "/v1/roles/permissions":
        result = matrix_data()
    elif path.startswith("/v1/roles/") and path.endswith("/permissions"):
        role = path.split("/")[-2]
        payload = route.request.post_data_json
        assert payload["version"] == versions[role]
        matrix[role] = payload["resources"]
        versions[role] += 1
        result = matrix_data()
    elif path == "/v1/users/meta/permission-directory":
        params = parse_qs(url.query)
        keyword = params.get("keyword", [""])[0]
        role_filter = params.get("role", [""])[0]
        page_number = int(params.get("page", ["1"])[0])
        size = int(params.get("size", ["20"])[0])
        matched = [user for user in users if keyword in user["username"]]
        counts = {role: sum(user["role"] == role for user in matched) for role in ROLE_ORDER}
        items = sorted([user for user in matched if not role_filter or user["role"] == role_filter], key=lambda user: (ROLE_ORDER.index(user["role"]), user["username"], user["id"]))
        result = {"items": items[(page_number - 1) * size:page_number * size], "total": len(items), "page": page_number, "size": size, "role_counts": counts}
    elif path.startswith("/v1/users/") and path.endswith("/permissions"):
        user_id = path.split("/")[-2]
        user = next(user for user in users if user["id"] == user_id)
        if method == "PUT":
            payload = route.request.post_data_json
            assert payload["version"] == user_versions[user_id]
            assert payload["expected_role"] == user["role"]
            user["role"] = payload["role"]
            overrides[user_id] = payload["overrides"]
            user_versions[user_id] += 1
        result = user_data(user)
    elif path.endswith("pending-work-items") or "summary" in path:
        result = {"pending_count": 0, "total": 0, "items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"code": "ok", "message": "", "data": result}, ensure_ascii=False))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1065}, device_scale_factor=1)
    page.set_default_timeout(10000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/v1/**", handle)
    page.add_init_script("""for (const [key, value] of Object.entries({piap_token:'test',piap_role:'admin',piap_roles:'["admin"]',piap_user_id:'admin',piap_org_id:'org',piap_username:'系统管理员'})) sessionStorage.setItem(key,value);""")
    base_url = os.environ.get("PIAP_PERMISSION_BASE_URL", "http://127.0.0.1:5173")
    page.goto(f"{base_url}/governance/admin/roles-orgs")
    page.wait_for_load_state("networkidle")
    panel = page.locator(".permission-matrix")
    grant_dialog = page.get_by_role("dialog", name="额外授权", exact=True)
    if panel.get_by_role("checkbox").count() == 0:
        print("Browser diagnostic:", page.url, page.locator("body").inner_text()[:3500], errors)
    def select_user(name):
        member = panel.get_by_role("button", name=name, exact=True, include_hidden=True)
        heading = member.locator("xpath=ancestor::section[1]").locator(".identity-heading")
        if heading.get_attribute("aria-expanded") == "false":
            heading.click()
        member.click()
        if name == "张三":
            expect(panel.get_by_role("button", name="算法与模型", exact=True)).to_be_visible()
            panel.get_by_role("button", name="算法与模型", exact=True).click()
    expect(panel.get_by_role("checkbox", name="算法工程师 数据集 管理")).to_be_checked()
    panel.get_by_role("checkbox", name="算法工程师 数据集 管理").uncheck()
    expect(panel.get_by_role("button", name="保存权限", exact=True)).to_be_enabled()
    panel.get_by_role("button", name="撤销未保存改动").click()
    expect(panel.get_by_role("checkbox", name="算法工程师 数据集 管理")).to_be_checked()
    panel.get_by_role("checkbox", name="算法工程师 数据集 管理").uncheck()
    panel.get_by_role("button", name="保存权限", exact=True).click()
    expect(panel.get_by_role("button", name="保存权限", exact=True)).to_be_disabled()
    page.reload()
    page.wait_for_load_state("networkidle")
    expect(panel.get_by_role("checkbox", name="算法工程师 数据集 管理")).not_to_be_checked()
    panel.get_by_role("checkbox", name="算法工程师 数据集 管理").check()
    panel.get_by_role("button", name="保存权限", exact=True).click()
    expect(panel.get_by_role("button", name="保存权限", exact=True)).to_be_disabled()
    panel.get_by_role("checkbox", name="算法工程师 模型配置 管理").uncheck()
    panel.get_by_role("button", name="保存权限", exact=True).click()
    expect(panel.get_by_role("button", name="保存权限", exact=True)).to_be_disabled()
    panel.locator(".entity-list .entity-button").filter(has_text="领域专家").click()
    expect(panel.get_by_role("button", name="人员与权限", exact=True)).to_have_count(0)
    expect(panel.get_by_role("button", name="算法与模型", exact=True)).to_have_count(0)
    expect(panel.get_by_role("checkbox", name="领域专家 异常反馈 使用")).not_to_be_checked()
    panel.get_by_role("checkbox", name="领域专家 异常反馈 使用").check()
    panel.get_by_role("button", name="保存权限", exact=True).click()
    expect(panel.get_by_role("button", name="保存权限", exact=True)).to_be_disabled()
    panel.get_by_label("搜索功能", exact=True).fill("用户管理")
    expect(panel.get_by_text("没有找到对应功能，请更换关键词。")).to_be_visible()
    panel.get_by_label("搜索功能", exact=True).fill("")
    panel.locator(".entity-list .entity-button").filter(has_text="管理员").click()
    panel.get_by_role("button", name="人员与权限", exact=True).click()
    expect(panel.get_by_role("checkbox", name="管理员 用户管理 管理")).to_be_checked()
    output = Path(os.environ.get("PIAP_PERMISSION_ARTIFACTS", str(Path(__file__).resolve().parents[1] / "test-results")))
    output.mkdir(parents=True, exist_ok=True)
    panel.locator(".entity-list .entity-button").filter(has_text="领域专家").click()
    page.screenshot(path=str(output / "permissions-expert-scope.png"), full_page=True)
    page.get_by_role("tab", name="用户授权", exact=True).click()
    expect(page.get_by_role("tab")).to_have_count(2)
    expect(panel.locator(".identity-heading").locator("strong")).to_have_text([ROLE_NAMES[key] for key in ROLE_ORDER])
    expect(panel.locator(".identity-group").filter(has=page.get_by_text("领域专家", exact=True)).locator(".identity-count")).to_have_text("4")
    select_user("张三")
    manage = panel.get_by_role("checkbox", name="允许模型配置管理", exact=True)
    expect(manage).not_to_be_checked()
    expect(page.locator(".el-message")).to_have_count(0)
    panel.get_by_role("button", name="额外授权", exact=True).click()
    expect(grant_dialog.get_by_role("checkbox", name="单独授予模型配置管理", exact=True)).to_be_visible()
    expect(grant_dialog.get_by_role("checkbox", name="单独授予用户管理管理", exact=True)).to_have_count(0)
    grant_dialog.get_by_role("checkbox", name="单独授予模型配置管理", exact=True).check()
    grant_dialog.get_by_role("button", name="取消", exact=True).click()
    expect(manage).not_to_be_checked()
    assert overrides["engineer"] == {}, "cancel must not change personal or server permissions"
    panel.get_by_role("button", name="额外授权", exact=True).click()
    grant_dialog.get_by_label("搜索可授权操作", exact=True).fill("不存在")
    expect(grant_dialog.get_by_text("没有匹配的操作，请更换关键词。")).to_be_visible()
    grant_dialog.get_by_label("搜索可授权操作", exact=True).fill("模型配置")
    grant_dialog.get_by_role("checkbox", name="单独授予模型配置管理", exact=True).check()
    page.screenshot(path=str(output / "permissions-extra-grant-dialog.png"), full_page=True, animations="disabled")
    grant_dialog.get_by_role("button", name="添加到待保存授权", exact=True).click()
    expect(manage).to_be_checked()
    assert overrides["engineer"] == {}, "dialog stages a draft; the page save persists it"
    row = panel.locator("tr").filter(has=page.get_by_text("模型配置", exact=True)).first
    expect(row.locator("td").nth(3).get_by_text("禁止", exact=True)).to_be_visible()
    expect(row.locator("td").nth(4).get_by_text("禁止 → 允许", exact=True)).to_be_visible()
    expect(panel.get_by_text("授予 模型配置·管理。", exact=True)).to_be_visible()
    output = Path(os.environ.get("PIAP_PERMISSION_ARTIFACTS", str(Path(__file__).resolve().parents[1] / "test-results")))
    output.mkdir(parents=True, exist_ok=True)
    expect(page.locator(".el-message")).to_have_count(0)
    panel.get_by_label("搜索功能", exact=True).fill("模型配置")
    for heading in panel.locator(".identity-heading").all():
        if "算法工程师" not in heading.inner_text() and heading.get_attribute("aria-expanded") == "true": heading.click()
    page.evaluate("document.querySelector('#main-content').scrollTop = 0")
    page.screenshot(path=str(output / "permissions-user-grant-preview.png"), full_page=True)
    panel.get_by_role("button", name="保存授权", exact=True).click()
    expect(panel.get_by_role("button", name="保存授权", exact=True)).to_be_disabled()
    assert overrides["engineer"]["model_config"] == "grant"
    assert "model_config" not in matrix["algorithm_engineer"]
    peer = next(user for user in users if user["id"] == "algorithm_engineer-1")
    assert "model_config" not in user_data(peer)["effective"], "extra grants must not affect a peer"
    panel.get_by_role("button", name="已额外授权 · 1", exact=True).click()
    expect(panel.get_by_text("额外授权", exact=True).locator("xpath=ancestor::div[contains(@class,'personal-operation')]")).to_be_visible()
    panel.get_by_role("button", name="全部权限", exact=True).click()
    manage.uncheck()
    expect(row.locator("td").nth(4).get_by_text("允许 → 禁止", exact=True)).to_be_visible()
    page.screenshot(path=str(output / "permissions-user-revoke-preview.png"), full_page=True)
    panel.get_by_role("button", name="保存授权", exact=True).click()
    expect(panel.get_by_role("button", name="保存授权", exact=True)).to_be_disabled()
    page.reload()
    page.wait_for_load_state("networkidle")
    page.get_by_role("tab", name="用户授权", exact=True).click()
    select_user("张三")
    expect(panel.get_by_role("checkbox", name="允许模型配置管理", exact=True)).not_to_be_checked()
    page.screenshot(path=str(output / "permissions-user.png"), full_page=True)
    select_user("李四")
    expect(panel.get_by_role("button", name="人员与权限", exact=True)).to_have_count(0)
    expect(panel.get_by_role("button", name="算法与模型", exact=True)).to_have_count(0)
    feedback = panel.get_by_role("checkbox", name="允许异常反馈使用", exact=True)
    expect(feedback).not_to_be_checked()
    assert overrides["ordinary"] == {} and matrix["user"] == [], "no prior personal revocation is required"
    panel.get_by_role("button", name="额外授权", exact=True).click()
    grant_dialog.get_by_role("checkbox", name="单独授予异常反馈使用", exact=True).check()
    grant_dialog.get_by_role("button", name="添加到待保存授权", exact=True).click()
    panel.get_by_role("button", name="保存授权", exact=True).click()
    expect(panel.get_by_role("button", name="保存授权", exact=True)).to_be_disabled()
    panel.get_by_label("用户角色", exact=True).select_option("expert")
    panel.get_by_role("button", name="保存授权", exact=True).click()
    expect(panel.get_by_role("button", name="保存授权", exact=True)).to_be_disabled()
    page.reload()
    page.wait_for_load_state("networkidle")
    page.get_by_role("tab", name="用户授权", exact=True).click()
    select_user("李四")
    expect(panel.get_by_label("用户角色", exact=True)).to_have_value("expert")
    expect(feedback).to_be_checked()
    feedback.uncheck()
    panel.get_by_role("button", name="保存授权", exact=True).click()
    expect(panel.get_by_role("button", name="保存授权", exact=True)).to_be_disabled()
    panel.get_by_role("button", name="额外授权", exact=True).click()
    expect(grant_dialog.get_by_text("当前没有可新增的额外权限", exact=True)).to_be_visible()
    grant_dialog.get_by_role("button", name="恢复已撤销 · 1", exact=True).click()
    grant_dialog.get_by_role("checkbox", name="单独授予异常反馈使用", exact=True).check()
    grant_dialog.get_by_role("button", name="添加到待保存授权", exact=True).click()
    expect(feedback).to_be_checked()
    panel.get_by_role("button", name="撤销未保存改动").click()
    expect(feedback).not_to_be_checked()
    panel.get_by_role("button", name="恢复异常反馈角色默认", exact=True).click()
    expect(feedback).to_be_checked()
    panel.get_by_role("button", name="撤销未保存改动").click()
    expect(feedback).not_to_be_checked()
    panel.get_by_role("button", name="恢复异常反馈角色默认", exact=True).click()
    panel.get_by_role("button", name="保存授权", exact=True).click()
    expect(panel.get_by_role("button", name="保存授权", exact=True)).to_be_disabled()
    panel.get_by_role("button", name="额外授权", exact=True).click()
    expect(grant_dialog.get_by_text("当前没有可新增的额外权限", exact=True)).to_be_visible()
    grant_dialog.get_by_role("button", name="固定保留已有权限 · 1", exact=True).click()
    grant_dialog.get_by_role("checkbox", name="单独授予异常反馈使用", exact=True).check()
    grant_dialog.get_by_role("button", name="添加到待保存授权", exact=True).click()
    expect(panel.locator(".personal-operation").get_by_text("个人固定授权", exact=True)).to_be_visible()
    expect(panel.get_by_text("当前可执行权限不变，仅修改跟随角色或个人设置方式。", exact=True)).to_be_visible()
    panel.get_by_role("button", name="撤销未保存改动").click()
    select_user("系统管理员")
    expect(panel.get_by_role("button", name="额外授权", exact=True)).to_be_disabled()
    panel.get_by_role("button", name="算法与模型", exact=True).click()
    expect(panel.get_by_role("checkbox", name="允许模型配置管理", exact=True)).to_be_disabled()
    select_user("张三")
    panel.get_by_label("搜索功能", exact=True).fill("不存在")
    expect(panel.get_by_text("没有找到对应功能，请更换关键词。")).to_be_visible()
    panel.get_by_label("搜索功能", exact=True).fill("")
    panel.get_by_label("身份筛选", exact=True).select_option("expert")
    expect(panel.locator(".identity-heading strong")).to_have_text(["领域专家"])
    expect(panel.locator(".identity-count")).to_have_text("5")
    expert_group = panel.get_by_role("region", name="领域专家用户组", exact=True)
    expert_group.get_by_role("button", name="领域专家 5").click()
    expect(expert_group.locator(".identity-members")).to_be_hidden()
    expert_group.get_by_role("button", name="领域专家 5").click()
    expect(expert_group.locator(".identity-members")).to_be_visible()
    panel.get_by_label("搜索用户", exact=True).fill("expert3")
    expect(panel.locator(".user-entity")).to_have_count(1)
    expect(panel.get_by_role("button", name="expert3", exact=True)).to_be_visible()
    panel.get_by_label("搜索用户", exact=True).fill("")
    expect(panel.locator(".user-entity")).to_have_count(5)
    panel.get_by_label("身份筛选", exact=True).select_option("")
    expect(panel.locator(".user-entity")).to_have_count(20)
    panel.get_by_role("button", name="下一页用户").click()
    expect(panel.locator(".user-entity")).to_have_count(3)
    panel.get_by_role("button", name="上一页用户").click()
    expect(panel.locator(".user-entity")).to_have_count(20)
    select_user("张三")
    expect(page.locator(".el-message")).to_have_count(0)
    for heading in panel.locator(".identity-heading").all():
        if "算法工程师" not in heading.inner_text() and heading.get_attribute("aria-expanded") == "true":
            heading.click()
    page.evaluate("document.querySelector('#main-content').scrollTop = 0; document.querySelector('.user-directory').scrollTop = 0")
    page.screenshot(path=str(output / "permissions-grouped-user.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right <= 0")
    page.screenshot(path=str(output / "permissions-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "page-level horizontal overflow"
    panel.get_by_role("button", name="额外授权", exact=True).click()
    expect(grant_dialog).to_be_visible()
    bounds = grant_dialog.bounding_box()
    assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
    page.screenshot(path=str(output / "permissions-extra-grant-mobile.png"), full_page=True, animations="disabled")
    grant_dialog.get_by_role("button", name="取消", exact=True).click()
    assert not errors, errors
    browser.close()
    print("PASS: extra grant dialog without prior denial, cancel/draft/save/reload/peer isolation, grant sources and filters, recovery vs fixing existing rights, role grant/revoke and assignment, inheritance, admin protection, grouped user directory and mobile layout")
