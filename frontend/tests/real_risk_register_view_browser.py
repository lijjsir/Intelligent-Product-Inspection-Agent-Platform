"""Read-only check of actual register columns and cards against local API data."""
import json
from pathlib import Path
from playwright.sync_api import expect,sync_playwright
ROOT=Path(__file__).resolve().parents[2]
auth=json.loads((ROOT/'backend/runtime/local_quality_release/private-register-session.json').read_text(encoding='utf-8'))
index=json.loads((ROOT/'backend/runtime/real_quality_case_20261023/case-index.json').read_text(encoding='utf-8'))
OUT=ROOT/'frontend/test-results/risk-register-responsive';errors=[];writes=[]
def guard(route):
    if route.request.method not in {'GET','HEAD','OPTIONS'}:writes.append(route.request.url);route.abort()
    else:route.continue_()
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':1000})
    context.add_init_script('for(const[k,v]of Object.entries('+json.dumps(auth)+'))sessionStorage.setItem(k,v)')
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.route('**/api/v1/**',guard)
    page.goto('http://127.0.0.1:5173/app/risk-assessments?case_id='+index['cases']['main'],wait_until='networkidle')
    detail=page.locator('#risk-case-detail');expect(detail).to_contain_text('JG2128520085')
    title=detail.locator('.detail-head h2').inner_text()
    detail.get_by_role('button',name='返回台账',exact=True).click()
    table=page.locator('#risk-case-register .case-table')
    for label in ['编号','风险对象','范围','证据','状态']:expect(table.get_by_role('columnheader',name=label,exact=True)).to_be_visible()
    assert table.locator('.el-scrollbar__wrap').first.evaluate('(element)=>element.scrollWidth<=element.clientWidth+1')
    page.screenshot(path=str(OUT/'real-register-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':1000})
    page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=0")
    cards=page.locator('#risk-case-register .case-cards');expect(cards).to_be_visible();expect(cards).to_contain_text(title)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(OUT/'real-register-mobile.png'),full_page=True)
    assert not errors and not writes,{'errors':errors,'writes':writes}
    result={'passed':True,'mode':'real local API; read-only','all_columns_visible':True,'mobile_fields_visible':True,'page_errors':errors,'business_writes':writes}
    (OUT/'real-checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    context.close();browser.close()
