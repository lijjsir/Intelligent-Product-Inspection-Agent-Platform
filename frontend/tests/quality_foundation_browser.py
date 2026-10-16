"""Verify the foundation redesign against the live API in an isolated test tenant."""
import json
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[2]
state = json.loads((root / 'backend/runtime/quality_intake_stage1/auth.json').read_text(encoding='utf-8'))
admin = state['identities']['admin']
output = root / 'frontend/test-results/quality-foundation'
output.mkdir(parents=True, exist_ok=True)
checks, errors = [], []
name = '隔离验证企业' + uuid4().hex[:6]
category_name = '电线电缆'

def field(dialog, label):
    return dialog.locator('.el-form-item').filter(has_text=label).locator('input').first

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.on('pageerror', lambda e: errors.append(str(e)))
    session = {'piap_token': admin['token'], 'piap_role': 'admin', 'piap_roles': '["admin"]',
               'piap_user_id': admin['user_id'], 'piap_org_id': admin['org_id'], 'piap_username': admin['username']}
    page.add_init_script('for(const [k,v] of Object.entries(' + json.dumps(session) + '))sessionStorage.setItem(k,v);')
    page.goto('http://127.0.0.1:5173/governance/admin/enterprises')
    page.wait_for_load_state('networkidle')
    if not page.locator('aside').get_by_text('产品目录', exact=True).is_visible():
        page.get_by_text('质监基础', exact=True).click()
    menu = page.locator('aside').inner_text()
    assert '自动接入设置' not in menu and '产品目录' in menu
    page.get_by_role('button', name='新增企业', exact=True).click()
    dialog = page.get_by_role('dialog', name='新增企业档案', exact=True)
    expect(dialog).to_be_visible()
    assert '企业角色' not in dialog.inner_text() and '定位并填写地址' not in dialog.inner_text()
    field(dialog, '企业名称').fill(name)
    page.screenshot(path=str(output / 'enterprise-form.png'), full_page=True)
    dialog.get_by_role('button', name='保存', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator('.el-table').get_by_text(name, exact=True)).to_be_visible()
    checks.append('真实企业创建：只填名称，无角色或定位要求')

    page.get_by_role('button', name='批量导入', exact=True).click()
    dialog = page.get_by_role('dialog', name='导入企业档案', exact=True)
    csv = f'企业名称,统一社会信用代码,详细地址\n{name}-导入甲,,\n{name}-导入乙,,\n'.encode('utf-8-sig')
    dialog.locator('input[type=file]').set_input_files({'name': 'enterprise.csv', 'mimeType': 'text/csv', 'buffer': csv})
    dialog.get_by_role('button', name='校验与预览', exact=True).click()
    expect(dialog.get_by_role('button', name='确认导入', exact=True)).to_be_enabled()
    dialog.get_by_role('button', name='确认导入', exact=True).click()
    expect(dialog).not_to_be_visible()
    checks.append('真实CSV企业批量导入，两行均无需人工编号')

    page.goto('http://127.0.0.1:5173/governance/admin/quality-products')
    page.wait_for_load_state('networkidle')
    expect(page.get_by_role('heading', name='产品目录', exact=True)).to_be_visible()
    expect(page.get_by_role('tab', name='产品列表', exact=True)).to_be_visible()
    page.get_by_role('tab', name='类别管理', exact=True).click()
    page.get_by_role('button', name='新增类别', exact=True).click()
    dialog = page.get_by_role('dialog', name='新增产品类别', exact=True)
    expect(dialog).to_be_visible()
    assert dialog.locator('.el-form-item__label').all_text_contents() == ['类别名称', '分类依据']
    field(dialog, '类别名称').fill(category_name)
    dialog.locator('textarea').fill('隔离验证分类目录，电线电缆条目')
    dialog.get_by_role('button', name='保存类别', exact=True).click()
    expect(dialog).not_to_be_visible()
    checks.append('真实类别创建：平级类别，只填名称、自动编号')

    page.get_by_role('tab', name='产品列表', exact=True).click()
    page.get_by_role('button', name='新增具体产品', exact=True).click()
    dialog = page.get_by_role('dialog', name='新增具体产品', exact=True)
    field(dialog, '具体产品名称').fill('隔离验证电缆')
    dialog.locator('.el-form-item').filter(has_text='所属类别').locator('.el-select').click()
    page.get_by_role('option', name=category_name, exact=True).click()
    assert '扩展属性' not in dialog.inner_text()
    field(dialog, '生产企业（选填）').fill(name)
    page.get_by_role('option', name=name, exact=True).click()
    dialog.get_by_role('button', name='保存产品', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator('.el-table').get_by_text(name, exact=True)).to_be_visible()
    page.screenshot(path=str(output / 'product-directory.png'), full_page=True)
    checks.append('真实产品创建：类别/企业关联、品牌型号可空、无需JSON')

    row = page.locator('.el-table__row').filter(has_text='隔离验证电缆')
    row.get_by_role('button', name='详情', exact=True).click()
    detail = page.get_by_role('dialog', name='产品详情', exact=True)
    detail.get_by_role('tab', name='批次', exact=True).click()
    detail.get_by_role('button', name='新增批次', exact=True).click()
    dialog = page.get_by_role('dialog', name='新增批次', exact=True)
    dialog.get_by_role('button', name='保存', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(detail.locator('.el-table__row')).to_have_count(1)
    first_number = detail.locator('.el-table__row').inner_text()
    assert 'PC-' in first_number and '未提供' in first_number
    detail.get_by_role('button', name='编辑', exact=True).click()
    dialog = page.get_by_role('dialog', name='编辑批次', exact=True)
    field(dialog, '原始批次号（选填）').fill('000007')
    dialog.get_by_role('button', name='保存', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(detail.get_by_text('000007', exact=True)).to_be_visible()
    page.screenshot(path=str(output / 'product-batches.png'), full_page=True)
    checks.append('真实批次创建和编辑：未知值留空、系统编号独立、原始编号保留前导零')
    detail.get_by_role('button', name='关联记录', exact=True).click()
    expect(detail.get_by_role('tab', name='关联记录', exact=True)).to_have_attribute('aria-selected', 'true')
    checks.append('产品详情可查看所选批次的关联记录')

    page.goto('http://127.0.0.1:5173/governance/admin/quality-data-sources')
    page.wait_for_load_state('networkidle')
    expect(page.get_by_role('heading', name='产品目录', exact=True)).to_be_visible()
    checks.append('旧自动接入页面地址跳转产品目录')
    assert not errors, errors
    browser.close()

with httpx.Client(base_url='http://127.0.0.1:8000/api/v1') as client:
    response = client.get('/enterprises', headers={'Authorization': 'Bearer ' + admin['token']}, params={'keyword': name})
    response.raise_for_status()
    records = response.json()['data']['items']
    assert len(records) == 3 and all(r['data']['role'] is None for r in records)
    assert all(r['display_no'].startswith('QY-') for r in records)
    checks.append('真实数据库核验：三家企业均有系统编号，身份保持未知')

(output / 'validation.json').write_text(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checks': checks, 'page_errors': errors}, ensure_ascii=True))
