"""Check first-batch creation through the live UI in the disposable intake test tenant."""
import json
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
state = json.loads((ROOT / "backend/runtime/quality_intake_stage1/auth.json").read_text(encoding="utf-8"))
admin = state["identities"]["admin"]
OUTPUT = ROOT / "frontend/test-results/quality-initial-batch"
OUTPUT.mkdir(parents=True, exist_ok=True)
suffix = uuid4().hex[:8]
errors, checks = [], []


def field(dialog, label):
    return dialog.locator(".el-form-item").filter(has_text=label).locator("input").first


with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", headers={"Authorization": "Bearer " + admin["token"]}, timeout=30) as api:
    category_response = api.post("/quality-products/categories", json={"name": "批次入口验证-" + suffix})
    category_response.raise_for_status()
    category = category_response.json()["data"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        session = {"piap_token": admin["token"], "piap_role": "admin", "piap_roles": '["admin"]',
                   "piap_user_id": admin["user_id"], "piap_org_id": admin["org_id"], "piap_username": admin["username"]}
        page.add_init_script("for(const [k,v] of Object.entries(" + json.dumps(session) + "))sessionStorage.setItem(k,v);")
        page.goto("http://127.0.0.1:5173/governance/admin/quality-products")
        page.wait_for_load_state("networkidle")

        def create_product(name, batch_no="", production_date=""):
            page.get_by_role("button", name="新增具体产品", exact=True).click()
            dialog = page.get_by_role("dialog", name="新增具体产品", exact=True)
            expect(dialog.get_by_role("heading", name="批次信息（选填）", exact=True)).to_be_visible()
            field(dialog, "具体产品名称").fill(name)
            dialog.locator(".el-form-item").filter(has_text="所属类别").locator(".el-select").click()
            page.get_by_role("option", name=category["name"], exact=True).click()
            expect(field(dialog, "原始批次号（选填）")).to_have_value("")
            expect(field(dialog, "生产日期（选填）")).to_have_value("")
            field(dialog, "原始批次号（选填）").fill(batch_no)
            if production_date:
                field(dialog, "生产日期（选填）").fill(production_date)
                field(dialog, "生产日期（选填）").press("Tab")
            if batch_no:
                page.screenshot(path=str(OUTPUT / "create-with-batch.png"), full_page=True)
            with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/quality-products")) as saved:
                dialog.get_by_role("button", name="保存产品", exact=True).click()
                duplicate = page.get_by_role("dialog", name="核对疑似重复产品", exact=True)
                if duplicate.is_visible():
                    duplicate.get_by_role("button", name="确认不同，继续新建", exact=True).click()
            assert saved.value.status == 201, saved.value.status
            expect(dialog).not_to_be_visible()
            return saved.value.json()["data"]

        first = create_product("空批次线缆-" + suffix)
        assert api.get(f'/quality-products/{first["id"]}/batches').json()["data"] == []
        checks.append("新增产品时两项留空，保存成功且不生成批次")
        second = create_product("有标签螺母-" + uuid4().hex[:8], "00001234", "2026-10-04")
        batches = api.get(f'/quality-products/{second["id"]}/batches').json()["data"]
        assert len(batches) == 1 and batches[0]["original_batch_no"] == "00001234"
        assert batches[0]["production_date"] == "2026-10-04" and batches[0]["display_no"].startswith("PC-")
        search = page.get_by_placeholder("搜索产品、品牌、型号或批次号", exact=True)
        for number in ("00001234", batches[0]["display_no"].lower()):
            search.fill(number)
            expect(page.locator(".catalog-card .el-table__row")).to_have_count(1)
            expect(page.locator(".catalog-card .el-table__row").get_by_text(second["name"], exact=True)).to_be_visible()
        assert batches[0]["display_no"] not in page.locator(".catalog-card .el-table__row").inner_text()
        page.set_viewport_size({"width": 1280, "height": 1000})
        scroll = page.locator(".catalog-card .el-table__body-wrapper .el-scrollbar__wrap")
        page.wait_for_function("el => el.scrollWidth <= el.clientWidth + 1", arg=scroll.element_handle(), timeout=3000)
        page.screenshot(path=str(OUTPUT / "catalog-batch-search.png"), full_page=True)
        widths = scroll.evaluate("el => ({content:el.scrollWidth, available:el.clientWidth})")
        assert widths["content"] <= widths["available"] + 1, widths
        checks.append("主列表按两种批次编号均能找到产品，只显示原始批号和数量，1280px宽度无横向溢出")
        row = page.locator(".el-table__row").filter(has_text=second["name"])
        row.get_by_role("button", name="1 个批次", exact=True).click()
        detail = page.get_by_role("dialog", name="产品详情", exact=True)
        expect(detail.get_by_text("00001234", exact=True)).to_be_visible()
        expect(detail.get_by_text(batches[0]["display_no"], exact=True)).to_be_visible()
        batch_search = detail.get_by_placeholder("搜索原始批次号或系统编号", exact=True)
        batch_search.fill(batches[0]["display_no"])
        expect(detail.locator(".el-table__row:visible")).to_have_count(1)
        batch_search.fill("没有这个批号")
        expect(detail.get_by_text("没有匹配的批次", exact=True)).to_be_visible()
        batch_search.fill("")
        page.screenshot(path=str(OUTPUT / "saved-batch.png"), full_page=True)
        checks.append("批次和产品一次保存，原始批次号保留前导零，系统编号自动生成，详情可见")
        detail.get_by_role("button", name="新增批次", exact=True).click()
        batch_dialog = page.get_by_role("dialog", name="新增批次", exact=True)
        field(batch_dialog, "原始批次号（选填）").fill("00005678")
        batch_dialog.get_by_role("button", name="保存", exact=True).click()
        expect(batch_dialog).not_to_be_visible()
        expect(page.locator(".catalog-card").get_by_role("button", name="2 个批次", exact=True)).to_have_count(1)
        known = detail.locator(".el-table__row:visible").filter(has_text="00001234")
        known.get_by_role("button", name="删除", exact=True).click()
        page.get_by_role("dialog", name="删除批次", exact=True).get_by_role("button", name="删除", exact=True).click()
        expect(detail.get_by_text("00001234", exact=True)).not_to_be_visible()
        page.keyboard.press("Escape")
        expect(detail).not_to_be_visible()
        expect(page.locator(".catalog-card .el-table__row")).to_have_count(0)
        search.fill("00005678")
        expect(page.locator(".catalog-card .el-table__row")).to_have_count(1)
        expect(page.locator(".catalog-card").get_by_role("button", name="1 个批次", exact=True)).to_be_visible()
        checks.append("详情可搜索两种批号；新增和删除批次后主列表数量及搜索结果同步更新")
        invalid_name = "非法日期验证-" + suffix
        invalid = api.post("/quality-products", json={"category_id": category["id"], "name": invalid_name,
            "initial_batch": {"production_date": "2026-99-99"}})
        assert invalid.status_code == 422
        assert not any(item["name"] == invalid_name for item in api.get("/quality-products/catalog").json()["data"]["products"])
        checks.append("非法生产日期在创建前拦截，不留下产品档案")
        assert not errors, errors
        browser.close()

report = {"checks": checks, "page_errors": errors}
(OUTPUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True))
