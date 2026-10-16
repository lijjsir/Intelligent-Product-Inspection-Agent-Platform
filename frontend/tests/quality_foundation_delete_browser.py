"""Exercise the actual delete buttons and reference protection against the local API."""
import json
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[2]
state = json.loads((root / 'backend/runtime/quality_intake_stage1/auth.json').read_text(encoding='utf-8'))
admin = state['identities']['admin']
output = root / 'frontend/test-results/quality-foundation-delete'
output.mkdir(parents=True, exist_ok=True)
checks, errors = [], []
name = '删除验证-' + uuid4().hex[:6]
headers = {'Authorization': 'Bearer ' + admin['token']}

with httpx.Client(base_url='http://127.0.0.1:8000/api/v1', headers=headers) as api:
    def create(path, data):
        response = api.post(path, json=data)
        response.raise_for_status()
        return response.json()['data']
    category = create('/quality-products/categories', {'name': '生漆', 'classification_basis': '隔离删除验证目录，生漆条目'})
    enterprise = create('/enterprises', {'name': name, 'data': {}})
    product = create('/quality-products', {'category_id': category['id'], 'name': name, 'model': 'A1', 'manufacturer_enterprise_id': enterprise['id']})
    batch = create(f"/quality-products/{product['id']}/batches", {'original_batch_no': '0001'})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        session = {'piap_token': admin['token'], 'piap_role': 'admin', 'piap_roles': '["admin"]',
                   'piap_user_id': admin['user_id'], 'piap_org_id': admin['org_id'], 'piap_username': admin['username']}
        page.add_init_script('for(const [k,v] of Object.entries(' + json.dumps(session) + '))sessionStorage.setItem(k,v);')

        def confirm():
            box = page.locator('.el-message-box')
            expect(box).to_be_visible()
            box.get_by_role('button', name='删除', exact=True).click()

        page.goto('http://127.0.0.1:5173/governance/admin/quality-products')
        page.wait_for_load_state('networkidle')
        row = page.locator('.el-table__row').filter(has_text=name)
        row.get_by_role('button', name='删除', exact=True).click()
        page.locator('.el-message-box').get_by_role('button', name='取消', exact=True).click()
        expect(row).to_have_count(1)
        row.get_by_role('button', name='删除', exact=True).click()
        confirm()
        expect(page.get_by_text('无法删除：该记录已关联产品批次，请先删除未使用的批次。不会连带删除关联数据。', exact=True)).to_be_visible()
        assert api.get(f"/quality-products/{product['id']}/batches").json()['data'][0]['id'] == batch['id']
        checks.append('取消不删除；有批次的产品被后端拦截，批次保持完整')

        row.get_by_role('button', name='详情', exact=True).click()
        detail = page.get_by_role('dialog', name='产品详情', exact=True)
        detail.get_by_role('tab', name='批次', exact=True).click()
        detail.get_by_role('button', name='删除', exact=True).click()
        confirm()
        expect(detail.get_by_text('暂无已登记批次', exact=True)).to_be_visible()
        detail.locator('.el-drawer__close-btn').click()
        expect(detail).not_to_be_visible()
        row.get_by_role('button', name='删除', exact=True).click()
        confirm()
        expect(row).to_have_count(0)
        checks.append('真实批次删除、产品删除，列表与详情同步更新')

        page.get_by_role('tab', name='类别管理', exact=True).click()
        page.locator('.el-table__row').filter(has_text='生漆').get_by_role('button', name='删除', exact=True).click()
        confirm()
        expect(page.locator('.el-table__row').filter(has_text='生漆')).to_have_count(0)
        checks.append('真实类别删除')

        page.goto('http://127.0.0.1:5173/governance/admin/enterprises')
        page.wait_for_load_state('networkidle')
        page.locator('.el-table__row').filter(has_text=name).get_by_role('button', name='删除', exact=True).click()
        confirm()
        expect(page.locator('.el-table__row').filter(has_text=name)).to_have_count(0)
        checks.append('真实企业删除')
        page.screenshot(path=str(output / 'enterprise-delete.png'), full_page=True)
        assert not errors, errors
        browser.close()

    assert api.get(f"/quality-products/{product['id']}/batches").status_code == 404
    assert api.get(f"/enterprises/{enterprise['id']}").status_code == 404
    catalog = api.get('/quality-products/catalog').json()['data']
    assert category['id'] not in {r['id'] for r in catalog['categories']}
    assert product['id'] not in {r['id'] for r in catalog['products']}
    checks.append('真实API重新查询确认四种记录均已删除')

(output / 'validation.json').write_text(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=True))
