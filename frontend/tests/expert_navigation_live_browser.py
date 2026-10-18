"""Read-only expert navigation checks against the real local demo API."""
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'.codex_tmp/piap_quality_demo'
config = json.loads((OUT/'accounts.json').read_text(encoding='utf-8'))
BASE = config['url']
account = next(a for a in config['accounts'] if a['username'] == 'demo_analyst')
errors, failures = [], []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':1500, 'height':1000}, timezone_id='Asia/Shanghai')
    page.on('pageerror', lambda e:errors.append(str(e)))
    page.on('response', lambda r:failures.append({'status':r.status,'path':urlparse(r.url).path}) if r.status >= 500 else None)
    page.goto(BASE+'/login', wait_until='networkidle')
    page.locator('#login-username').fill(account['username'])
    page.locator('#login-password').fill(account['password'])
    page.get_by_role('button', name='登录', exact=False).click()
    page.wait_for_url('**/app/workbench')
    page.wait_for_load_state('networkidle')
    sidebar = page.locator('.app-sidebar')
    nav = sidebar.locator('nav')
    roots = nav.evaluate("node => Array.from(node.children).map(e => e.classList.contains('nav-group') ? e.querySelector('button').innerText.trim() : e.innerText.trim()).filter(Boolean)")
    assert roots == ['质监工作台', '质量监督', '实验室检测', '标准与知识', 'AI 对话', '个人设置'], roots
    assert nav.locator('.nav-group-link[aria-expanded=true]').count() == 0
    nav.get_by_role('button', name='质量监督', exact=True).click()
    assert page.url == BASE+'/app/workbench'
    expect(nav.get_by_role('button', name='质量监督', exact=True)).to_have_attribute('aria-expanded','true')
    assert nav.locator('#nav-group-质量监督 a').all_text_contents() == ['数据采集','市场监控','风险研判','监督抽查','协同中心','报告中心']
    sidebar.screenshot(path=str(OUT/'navigation-expert-desktop.png'))
    nav.get_by_role('button', name='实验室检测', exact=True).click()
    assert page.url == BASE+'/app/workbench'
    expect(nav.get_by_role('button', name='质量监督', exact=True)).to_have_attribute('aria-expanded','false')
    assert nav.locator('#nav-group-实验室检测 a').all_text_contents() == ['实验室工作台','检测任务','检测结果']
    nav.get_by_role('link', name='检测任务', exact=True).click()
    page.wait_for_url('**/app/tasks')
    expect(nav.locator('.nav-link-active')).to_have_text('检测任务')
    nav.get_by_role('button', name='标准与知识', exact=True).click()
    assert page.url == BASE+'/app/tasks'
    assert nav.locator('.nav-group-link[aria-expanded=true]').count() == 1
    expect(nav.get_by_role('link', name='标准审核', exact=True)).to_be_visible()
    expect(nav.get_by_role('link', name='知识资料', exact=True)).to_be_visible()
    page.goto(BASE+'/app/risk-sampling', wait_until='networkidle')
    expect(nav.get_by_role('button', name='质量监督', exact=True)).to_have_attribute('aria-expanded','true')
    expect(nav.locator('.nav-link-active')).to_have_text('监督抽查')
    page.reload(wait_until='networkidle')
    expect(nav.locator('.nav-link-active')).to_have_text('监督抽查')
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button', name='打开导航', exact=True).click()
    expect(sidebar).to_have_class(__import__('re').compile('mobile-nav-open'))
    nav.get_by_role('button', name='实验室检测', exact=True).click()
    expect(nav.get_by_role('button', name='质量监督', exact=True)).to_have_attribute('aria-expanded','false')
    assert page.url == BASE+'/app/risk-sampling'
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(OUT/'navigation-expert-mobile.png'))
    assert not errors and not failures, (errors, failures)
    result = {'passed':True, 'api_mode':'real local demo API', 'expert_landing':'/app/workbench',
        'root_order':roots, 'disclosure_does_not_navigate':True, 'exclusive_groups':True,
        'task_highlight_and_suggestion_deep_link':True, 'desktop_mobile_verified':True,
        'business_mutations_performed':False, 'page_errors':errors, 'http_5xx':failures}
    (OUT/'navigation-checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    browser.close()
