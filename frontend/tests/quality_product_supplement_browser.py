"""Live validation of optional classification basis and supplementing sparse product records."""
import json
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[2]
admin = json.loads((root / 'backend/runtime/quality_intake_stage1/auth.json').read_text(encoding='utf-8'))['identities']['admin']
headers = {'Authorization': 'Bearer ' + admin['token']}
output = root / 'frontend/test-results/quality-product-supplement'
output.mkdir(parents=True, exist_ok=True)
suffix = uuid4().hex[:6]
checks, errors = [], []

with httpx.Client(base_url='http://127.0.0.1:8000/api/v1', headers=headers, timeout=60) as api:
    def post(path, payload):
        response = api.post(path, json=payload)
        response.raise_for_status()
        return response.json()['data']
    category = post('/quality-products/categories', {'name': '紧固件-' + suffix})
    assert category['classification_basis'] is None
    product = post('/quality-products', {'category_id': category['id'], 'name': '螺栓-' + suffix, 'brand': '已有品牌'})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        session = {'piap_token': admin['token'], 'piap_role': 'admin', 'piap_roles': '["admin"]',
                   'piap_user_id': admin['user_id'], 'piap_org_id': admin['org_id'], 'piap_username': admin['username']}
        page.add_init_script('for(const [k,v] of Object.entries(' + json.dumps(session) + '))sessionStorage.setItem(k,v);')
        page.goto('http://127.0.0.1:5173/governance/admin/quality-products')
        page.wait_for_load_state('networkidle')
        page.get_by_role('tab', name='类别管理', exact=True).click()
        row = page.locator('.el-table__row').filter(has_text=category['name'])
        expect(row.get_by_text('依据待补充', exact=True)).to_be_visible()
        page.get_by_role('button', name='新增类别', exact=True).click()
        dialog = page.get_by_role('dialog', name='新增产品类别', exact=True)
        assert dialog.locator('.el-form-item.is-required .el-form-item__label').all_text_contents() == ['类别名称']
        dialog.locator('summary').click()
        expect(dialog.get_by_text('查看示例出处', exact=True)).to_be_visible()
        page.screenshot(path=str(output / 'basis-example.png'), full_page=True)
        dialog.locator('input[type=text]').fill('待补依据类别-' + suffix)
        dialog.get_by_role('button', name='保存类别', exact=True).click()
        expect(dialog).not_to_be_visible()
        new_category = next(r for r in api.get('/quality-products/catalog').json()['data']['categories'] if r['name'] == '待补依据类别-' + suffix)
        assert new_category['classification_basis'] is None
        checks.append('分类依据可留空保存，标注待补充，表单提供电线电缆示例与出处')

        page.get_by_role('tab', name='产品列表', exact=True).click()
        page.get_by_role('button', name='新增具体产品', exact=True).click()
        dialog = page.get_by_role('dialog', name='新增具体产品', exact=True)
        dialog.locator('.el-form-item').filter(has_text='具体产品名称').locator('input').fill(product['name'])
        dialog.locator('.el-form-item').filter(has_text='所属类别').locator('.el-select input').first.fill(category['name'])
        page.get_by_role('option', name=category['name'], exact=True).click()
        dialog.locator('.el-form-item').filter(has_text='型号 / 规格').locator('input').fill('A1')
        panel = dialog.get_by_role('region', name='疑似已有产品档案')
        expect(panel).to_be_visible()
        expect(panel.get_by_text('已有品牌', exact=False)).to_be_visible()
        page.screenshot(path=str(output / 'duplicate-hint.png'), full_page=True)
        panel.get_by_role('button', name='补充此档案', exact=True).click()
        dialog = page.get_by_role('dialog', name='编辑具体产品', exact=True)
        expect(dialog).to_be_visible()
        assert dialog.locator('.el-form-item').filter(has_text='品牌（选填）').locator('input').input_value() == '已有品牌'
        assert dialog.locator('.el-form-item').filter(has_text='型号 / 规格').locator('input').input_value() == 'A1'
        dialog.get_by_role('button', name='保存产品', exact=True).click()
        expect(dialog).not_to_be_visible()
        catalog = api.get('/quality-products/catalog').json()['data']
        matches = [r for r in catalog['products'] if r['name'] == product['name']]
        assert len(matches) == 1 and matches[0]['id'] == product['id']
        assert matches[0]['brand'] == '已有品牌' and matches[0]['model'] == 'A1'
        checks.append('疑似重复提示可补充原档案，保留已有品牌和ID，补入型号，不新增第二条')
        assert not errors, errors
        browser.close()

(output / 'validation.json').write_text(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=True))
