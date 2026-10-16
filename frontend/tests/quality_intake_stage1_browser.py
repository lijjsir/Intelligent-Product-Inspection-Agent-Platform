"""Real local UI/API verification using the dedicated tenant fixture (no route mocks)."""
import json
import re
from uuid import uuid4
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[2]
fixture = json.loads((root / "backend/runtime/quality_intake_stage1/auth.json").read_text(encoding="utf-8"))
identity = fixture["identities"]["user"]
output = root / "frontend/test-results/quality-intake-stage1"
output.mkdir(parents=True, exist_ok=True)
csv_file = output / "browser-material.csv"
csv_file.write_text(f"原始内容,原始出处,生产批次,data_nature,external_record_id\n浏览器导入材料甲,来源甲,000123,synthetic,{uuid4()}\n浏览器导入材料乙,来源乙,000124,synthetic,{uuid4()}\n", encoding="utf-8-sig")
run_id=uuid4().hex[:8]
raw_text=f"浏览器隔离验证：产品使用后出现异常-{run_id}"
errors = []
checks = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, timezone_id="Asia/Shanghai")
    page.on("pageerror", lambda error: errors.append(str(error)))
    storage = {"piap_token": identity["token"], "piap_role": "user", "piap_roles": '["user"]',
               "piap_user_id": identity["user_id"], "piap_org_id": identity["org_id"], "piap_username": identity["username"]}
    page.add_init_script("for(const [key,value] of Object.entries(" + json.dumps(storage) + ")) sessionStorage.setItem(key,value);")
    page.goto("http://127.0.0.1:5173/app/tasks")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button", name="提交质量资料", exact=True)).to_have_count(0)
    page.goto("http://127.0.0.1:5173/app/chat")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="提交质量资料", exact=True).click()
    panel = page.get_by_role("dialog", name="提交与查看本人质量资料", exact=True)
    expect(panel.get_by_role("heading", name="本人质量资料", exact=True)).to_be_visible()
    panel.get_by_role("button", name="提交资料", exact=True).click()
    form = page.get_by_role("dialog", name="提交质量资料", exact=True)
    form.get_by_placeholder("保留原话或原始材料内容").fill(raw_text)
    form.get_by_role("button", name="提交", exact=True).click()
    expect(panel.get_by_text(raw_text, exact=True)).to_be_visible()
    assert panel.get_by_text(re.compile(r"ZL-\d{8}-\d{8}")).count() > 0
    assert form.get_by_text("请选择数据来源").count() == 0
    checks.append("普通用户从个人对话提交原文，检测任务无重复资料台账入口")
    panel.get_by_role("button", name="文件导入", exact=True).click()
    dialog = page.get_by_role("dialog", name="导入现有结构化资料", exact=True)
    dialog.locator('input[type="file"]').set_input_files(str(csv_file))
    dialog.get_by_role("button", name="校验并预览", exact=True).click()
    expect(dialog.get_by_text(re.compile(r"有效 2 条，错误 0 条"))).to_be_visible()
    expect(dialog.get_by_text("来源甲", exact=True)).to_be_visible()
    dialog.get_by_role("button", name="确认导入", exact=True).click()
    expect(dialog.get_by_text("已完成：新建 2，重复 0，失败 0", exact=True)).to_be_visible()
    dialog.get_by_role("button", name="关闭", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(panel.get_by_text("浏览器导入材料甲", exact=True).first).to_be_visible()
    checks.append("中文CSV预览、逐行出处和真实确认回执，列表可回查")
    page.screenshot(path=str(output / "desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    panel.get_by_role("button", name="提交资料", exact=True).click()
    expect(page.get_by_role("dialog", name="提交质量资料", exact=True)).to_be_visible()
    page.wait_for_timeout(300)
    page.screenshot(path=str(output / "mobile.png"), full_page=True)
    page.get_by_role("dialog", name="提交质量资料", exact=True).get_by_role("button", name="取消", exact=True).click()
    checks.append("390px下可打开提交表单，整页无横向溢出")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:5173/app/chat")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button", name="提交质量资料", exact=True)).to_be_visible()
    checks.append("AI对话保留明确提交入口，无新增普通用户资料导航")
    assert not errors, errors
    browser.close()

(output / "validation.json").write_text(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=True))
