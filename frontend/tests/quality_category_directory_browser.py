"""Live verification: define categories with basis, import them, select them for products."""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[2]
state = json.loads((root / 'backend/runtime/quality_intake_stage1/auth.json').read_text(encoding='utf-8'))
admin = state['identities']['admin']
headers = {'Authorization': 'Bearer ' + admin['token']}
base = 'http://127.0.0.1:8000/api/v1'
output = root / 'frontend/test-results/quality-category-directory'
output.mkdir(parents=True, exist_ok=True)
checks, errors = [], []
suffix = uuid4().hex[:6]
name = '工业紧固件-' + suffix
basis = '隔离验证用分类目录，工业紧固件条目'

with httpx.Client(base_url=base, headers=headers, timeout=60) as api:
    before = api.get('/quality-products/catalog').json()['data']
    response = api.post('/quality-products/categories', json={'name': '未记录依据的类别-' + suffix})
    assert response.status_code == 201 and response.json()['data']['classification_basis'] is None
    before = api.get('/quality-products/catalog').json()['data']
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
        expect(page.get_by_role('button', name='导入类别目录', exact=True)).to_have_count(0)
        expect(page.get_by_role('button', name='从目录加入类别', exact=True)).to_have_count(0)
        page.get_by_role('button', name='新增类别', exact=True).click()
        dialog = page.get_by_role('dialog', name='新增产品类别', exact=True)
        expect(dialog).to_be_visible()
        assert dialog.locator('.el-select').count() == 0
        assert dialog.locator('.el-form-item__label').all_text_contents() == ['类别名称', '分类依据（选填，可后补）']
        dialog.get_by_role('button', name='保存类别', exact=True).click()
        expect(page.get_by_text('请填写类别名称', exact=True)).to_be_visible()
        dialog.locator('input[type=text]').fill(name)
        dialog.locator('textarea').fill(basis)
        page.screenshot(path=str(output / 'new-category-form.png'), full_page=True)
        dialog.get_by_role('button', name='保存类别', exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(page.locator('.el-table').get_by_text(name, exact=True)).to_be_visible()
        category = next(row for row in api.get('/quality-products/catalog').json()['data']['categories'] if row['name'] == name)
        assert category['classification_basis'] == basis
        checks.append('目录外类别可新增；缺依据可先保存待补充，名称仍须填写')

        page.get_by_role('tab', name='产品列表', exact=True).click()
        page.get_by_role('button', name='新增具体产品', exact=True).click()
        dialog = page.get_by_role('dialog', name='新增具体产品', exact=True)
        dialog.locator('.el-form-item').filter(has_text='具体产品名称').locator('input').fill('螺栓产品-' + suffix)
        field = dialog.locator('.el-form-item').filter(has_text='所属类别').locator('.el-select input').first
        field.fill(name)
        page.get_by_role('option', name=name, exact=True).click()
        dialog.locator('.el-form-item').filter(has_text='具体产品名称').locator('input').click()
        page.screenshot(path=str(output / 'select-existing-category.png'), full_page=True)
        dialog.get_by_role('button', name='保存产品', exact=True).click()
        expect(dialog).not_to_be_visible()
        after = api.get('/quality-products/catalog').json()['data']
        product = next(row for row in after['products'] if row['name'] == '螺栓产品-' + suffix)
        assert product['category_id'] == category['id']
        assert len(after['categories']) == len(before['categories']) + 1
        checks.append('具体产品只选择已维护类别，保存产品不增加类别')

        page.get_by_role('tab', name='类别管理', exact=True).click()
        page.locator('.el-table__row').filter(has_text=name).get_by_role('button', name='编辑', exact=True).click()
        dialog = page.get_by_role('dialog', name='编辑产品类别', exact=True)
        dialog.locator('textarea').fill(basis + '，补充版本信息')
        dialog.get_by_role('button', name='保存类别', exact=True).click()
        expect(dialog).not_to_be_visible()
        checks.append('可以编辑类别名称和分类依据')

        page.get_by_role('button', name='新增类别', exact=True).click()
        dialog = page.get_by_role('dialog', name='新增产品类别', exact=True)
        dialog.get_by_text('文件批量导入', exact=True).click()
        dialog.locator('textarea').fill('隔离测试目录共同依据')
        csv = f'类别名称,分类依据\n金属材料-{suffix},逐行依据\n塑料制品-{suffix},\n{name},逐行依据\n'.encode('utf-8-sig')
        dialog.locator('input[type=file]').set_input_files({'name': 'categories.csv', 'mimeType': 'text/csv', 'buffer': csv})
        dialog.get_by_role('button', name='校验与预览', exact=True).click()
        expect(dialog.get_by_role('button', name='确认导入', exact=True)).to_be_enabled()
        dialog.get_by_role('button', name='确认导入', exact=True).click()
        expect(dialog).not_to_be_visible()
        after = api.get('/quality-products/catalog').json()['data']
        assert len([r for r in after['categories'] if r['name'] == name]) == 1
        assert next(r for r in after['categories'] if r['name'] == '金属材料-' + suffix)['classification_basis'] == '逐行依据'
        assert next(r for r in after['categories'] if r['name'] == '塑料制品-' + suffix)['classification_basis'] == '隔离测试目录共同依据'
        checks.append('真实CSV目录导入，逐行依据优先、共同依据补充、重复类别复用')
        page.get_by_role('button', name='新增类别', exact=True).click()
        dialog = page.get_by_role('dialog', name='新增产品类别', exact=True)
        expect(dialog.get_by_role('radio', name='手工填写', exact=True)).to_be_checked()
        dialog.get_by_text('文件批量导入', exact=True).click()
        assert dialog.locator('textarea').input_value() == ''
        expect(dialog.locator('.el-upload-list__item')).to_have_count(0)
        expect(dialog.get_by_role('button', name='确认导入', exact=True)).to_be_disabled()
        dialog.get_by_role('button', name='取消', exact=True).click()
        checks.append('主页面单一新增入口，重新打开默认手工填写且无上次导入文件')
        assert not errors, errors
        browser.close()

async def concurrency():
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=60) as api:
        results = await asyncio.gather(*[api.post('/quality-products/categories', json={'name': '并发工业类别-' + suffix, 'classification_basis': basis}) for _ in range(8)])
        assert all(result.status_code == 201 for result in results), [r.status_code for r in results]
        assert len({r.json()['data']['id'] for r in results}) == 1
        checks.append('8次真实并发新增同名类别只产生一条记录')

asyncio.run(concurrency())
(output / 'validation.json').write_text(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=True))
