"""Read the user-requested public examples from the actual main workspace without modifying them."""
import json
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[2]
auth_path = root / 'backend/runtime/industrial_catalog_view_auth.json'
session = json.loads(auth_path.read_text(encoding='utf-8'))
output = root / 'frontend/test-results/public-industrial-catalog'
output.mkdir(parents=True, exist_ok=True)
errors = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('for(const [k,v] of Object.entries(' + json.dumps(session) + '))sessionStorage.setItem(k,v);')
        page.goto('http://127.0.0.1:5173/governance/admin/quality-products')
        page.wait_for_load_state('networkidle')
        for model in ['NXB-63 1P C25', 'NM1-125S/3300 3P 100A', 'NC1-09', 'NXZN-250-3A']:
            row = page.locator('.el-table__row').filter(has_text=model)
            expect(row).to_have_count(1)
            expect(row.get_by_text('正泰', exact=True)).to_be_visible()
            expect(row.get_by_text('浙江正泰电器股份有限公司', exact=True)).to_be_visible()
        page.screenshot(path=str(output / 'products.png'), full_page=True)
        page.get_by_role('tab', name='类别管理', exact=True).click()
        for name in ['小型断路器', '塑料外壳式断路器', '交流接触器', '自动转换开关电器']:
            row = page.locator('.el-table__row').filter(has_text=name)
            expect(row).to_have_count(1)
            assert '依据待补充' not in row.inner_text()
        page.screenshot(path=str(output / 'categories.png'), full_page=True)
        page.goto('http://127.0.0.1:5173/governance/admin/enterprises')
        page.wait_for_load_state('networkidle')
        company = page.locator('.el-table__row').filter(has_text='浙江正泰电器股份有限公司')
        expect(company).to_have_count(1)
        expect(company.get_by_text('91330000142944445H', exact=True)).to_be_visible()
        company.get_by_role('button', name='查看 / 编辑', exact=True).click()
        dialog = page.get_by_role('dialog', name='编辑企业档案', exact=True)
        dialog.get_by_text('补充信息', exact=True).click()
        address = dialog.locator('.el-form-item').filter(has_text='详细地址').locator('input').input_value()
        assert address == '浙江省乐清市北白象镇正泰工业园区正泰路1号'
        page.screenshot(path=str(output / 'enterprise.png'), full_page=True)
        dialog.get_by_role('button', name='取消', exact=True).click()
        assert not errors, errors
        browser.close()
    print(json.dumps({'products': 4, 'categories': 4, 'enterprise': '浙江正泰电器股份有限公司', 'read_only_verified': True, 'page_errors': errors}, ensure_ascii=True))
finally:
    auth_path.unlink(missing_ok=True)
