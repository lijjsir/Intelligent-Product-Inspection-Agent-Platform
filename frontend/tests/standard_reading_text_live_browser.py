"""Verify repaired real PDF reading views without submitting reviews or writes."""
import json
import re
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'backend/runtime/standard_text_repair_20261023'
OUT=ROOT/'frontend/test-results/standard-reading-text-live'
OUT.mkdir(exist_ok=True,parents=True)
target=next(row for row in json.loads((DATA/'repair-result.json').read_text(encoding='utf-8')) if row['standard_no']=='GB/T 7707-2008')
auth=json.loads((DATA/'private-browser-session.json').read_text(encoding='utf-8'))
errors=[];writes=[]


def guard(route):
    request=route.request
    if request.method not in {'GET','HEAD','OPTIONS'} and not request.url.endswith('/streams/session'):
        writes.append(request.method+' '+request.url.split('/api/')[-1]);route.abort();return
    route.continue_()


with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1600,'height':1100})
    context.add_init_script('for(const[k,v]of Object.entries('+json.dumps(auth)+'))sessionStorage.setItem(k,v)')
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/api/v1/**',guard)
    page.goto('http://127.0.0.1:5173/app/standard-reviews?document_id='+target['document_id']+'&revision_id='+target['new_revision_id']+'&keyword=7707',wait_until='networkidle')
    dialog=page.get_by_role('dialog',name='标准原文与逐项核对',exact=True)
    expect(dialog).to_be_visible()
    card=dialog.locator('.requirement-card').filter(has=page.locator('header strong',has_text=re.compile(r'^5\.4\.4\.1 ')))
    expect(card).to_have_count(1)
    expect(card.locator('.candidate-reading')).to_contain_text('公式或特殊符号，请查看本页原件')
    expect(card.locator('.candidate-reading')).not_to_contain_text('犇')
    expect(card.locator('.extraction-details')).not_to_have_attribute('open','')
    card.get_by_role('button',name='查看本条原页',exact=True).click()
    preview=dialog.get_by_role('img',name='标准原件第6页',exact=True)
    expect(preview).to_be_visible()
    page.wait_for_function("Array.from(document.images).some(image=>image.alt==='标准原件第6页' && image.complete && image.naturalWidth>0)")
    expect(card.locator('.candidate-reading')).not_to_contain_text('玡')
    card.scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'actual-standard-reading-page6.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    card.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(OUT/'actual-standard-reading-mobile.png'),full_page=True)
    assert not errors and not writes, {'errors':errors,'writes':writes}
    report={'passed':True,'real_api':True,'document_id':target['document_id'],'revision_id':target['new_revision_id'],
        'original_pdf_page':6,'professional_reviews_submitted':0,'page_errors':errors,'business_writes':writes}
    (OUT/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    context.close();browser.close()
