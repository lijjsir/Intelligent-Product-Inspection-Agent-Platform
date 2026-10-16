"""Read the actual MVTec test catalogue and select it in the existing expert task form."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "backend/runtime/mvtec_catalog_view_auth.json"
manifest = json.loads((ROOT / "backend/scripts/data/mvtec_industrial_catalog_2026_10_04.json").read_text(encoding="utf-8"))
result = json.loads((ROOT / "backend/runtime/mvtec_industrial_catalog_2026_10_04_result.json").read_text(encoding="utf-8"))
sessions = json.loads(AUTH.read_text(encoding="utf-8"))
OUTPUT = ROOT / "frontend/test-results/mvtec-catalog"
OUTPUT.mkdir(parents=True, exist_ok=True)
errors, mutations = [], []
standard_names = {"bottle": "瓶子 检测标准", "cable": "电缆 检测标准", "carpet": "地毯 检测标准",
                  "grid": "网格 检测标准", "leather": "皮革 检测标准", "metal_nut": "金属螺母 检测标准",
                  "screw": "螺丝 检测标准", "tile": "瓷砖 检测标准", "toothbrush": "牙刷 检测标准",
                  "transistor": "晶体管 检测标准", "wood": "木材 检测标准", "zipper": "拉链 检测标准"}


def new_page(browser, role):
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    page.add_init_script("for(const [k,v] of Object.entries(" + json.dumps(sessions[role]) + "))sessionStorage.setItem(k,v);")
    page.on("pageerror", lambda error: errors.append(str(error)))
    # The app creates short-lived stream sessions on navigation; those do not change business data.
    page.on("request", lambda request: mutations.append({"method": request.method, "path": request.url.split("?")[0]})
            if "/api/v1/" in request.url and request.method in {"POST", "PATCH", "PUT", "DELETE"}
            and not request.url.split("?")[0].endswith("/api/v1/streams/session") else None)
    return context, page


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context, page = new_page(browser, "admin")
        page.goto("http://127.0.0.1:5173/governance/admin/quality-products")
        page.wait_for_load_state("networkidle")
        for item in manifest["items"]:
            row = page.locator(".el-table__row").filter(has_text=item["name"])
            expect(row).to_have_count(1)
            expect(row.get_by_text(item["category_name"], exact=True)).to_be_visible()
        page.screenshot(path=str(OUTPUT / "products.png"), full_page=True)
        row = page.locator(".el-table__row").filter(has_text=manifest["items"][1]["name"])
        row.get_by_role("button", name="详情", exact=True).click()
        detail = page.get_by_role("dialog", name="产品详情", exact=True)
        expect(detail.get_by_text("mvtec-ad:cable", exact=True)).to_be_visible()
        expect(detail.get_by_text("未提供", exact=True)).to_have_count(3)
        page.screenshot(path=str(OUTPUT / "cable-detail.png"), full_page=True)
        context.close()

        context, page = new_page(browser, "expert")
        page.goto("http://127.0.0.1:5173/app/tasks")
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="新建任务", exact=True).click()
        dialog = page.get_by_role("dialog", name="新建通用检测任务", exact=True)
        expect(dialog).to_be_visible()
        checked = []
        for item in manifest["items"]:
            category = dialog.locator(".el-form-item").filter(has=page.get_by_text("产品类别", exact=True)).get_by_role("combobox")
            category.fill(item["category_name"])
            option = page.locator(".el-select-dropdown__item:visible").filter(has_text=item["category_name"])
            expect(option).to_have_count(1)
            option.click()
            product_field = dialog.locator(".el-form-item").filter(has=page.get_by_text("具体产品 / 型号", exact=True))
            product = product_field.get_by_role("combobox")
            product.fill(item["name"])
            option = page.locator(".el-select-dropdown__item:visible").filter(has_text=item["name"])
            expect(option).to_have_count(1)
            option.click()
            standard = dialog.locator(".el-form-item").filter(has=page.get_by_text("检测标准", exact=True)).get_by_role("combobox")
            standard.fill(standard_names[item["folder"]])
            option = page.locator(".el-select-dropdown__item:visible").filter(has_text=standard_names[item["folder"]])
            expect(option).to_have_count(1)
            option.click()
            expect(product_field.get_by_text(item["name"], exact=True)).to_be_visible()
            checked.append(item["folder"])
        sample = next((Path(manifest["dataset_root"]) / "zipper/test/good").glob("*.png"))
        dialog.locator('input[type="file"]').set_input_files(str(sample))
        expect(dialog.locator(".el-upload-list__item")).to_have_count(1)
        page.screenshot(path=str(OUTPUT / "task-options.png"), full_page=True)
        dialog.get_by_role("button", name="取消", exact=True).click()
        assert not errors, errors
        assert not mutations, mutations
        context.close()
        browser.close()
        report = {"catalogue_products": 12, "expert_selectable_products": checked, "local_image_selectable": True,
                  "task_submitted": False, "api_business_mutations": mutations, "page_errors": errors}
        (OUTPUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report))
finally:
    AUTH.unlink(missing_ok=True)
