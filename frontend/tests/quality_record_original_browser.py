"""Exercise original comparison with public source files; intercept all API calls."""
from pathlib import Path
import hashlib
import json
import re
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / 'backend/runtime/real_quality_case_20261023'
OUT = ROOT / 'frontend/test-results/quality-record-original'
OUT.mkdir(parents=True, exist_ok=True)
facts = json.loads((SOURCES / 'public-package/public-facts-and-provenance.json').read_text(encoding='utf-8'))
report = next(f for f in facts if f['key'] == 'report')
charger = next(f for f in facts if f['key'] not in ['report', 'news', 'sampling', 'cq_enforcement'])
pdf = (SOURCES / 'sources/report.pdf').read_bytes()
txt = (SOURCES / 'sources/samr_2024.txt').read_bytes()
pdf_file = {'id': 'public-report', 'file_name': 'JG2128520085.pdf', 'mime_type': 'application/pdf', 'size_bytes': len(pdf), 'sha256': hashlib.sha256(pdf).hexdigest(), 'download_url': ''}
txt_file = {'id': 'public-text', 'file_name': '市场监管总局公开通报文字.txt', 'mime_type': 'text/plain', 'size_bytes': len(txt), 'sha256': hashlib.sha256(txt).hexdigest(), 'download_url': ''}
def record(fact, number, attachment):
    return {**fact, 'id': fact['local_record_id'], 'display_no': number, 'source_id': 'public', 'received_at': '2026-10-23T00:36:00', 'content_hash': 'fixture', 'enterprise_ref': {}, 'product_ref': {}, 'attachment_ids': [attachment['id']], 'authorization_scope': 'organization', 'normalization_status': 'pending', 'normalization_errors': [], 'created_by': 'expert'}
records = [record(report, 'ZL-20261023-00000003', pdf_file), record(charger, 'ZL-20261023-00000005', txt_file)]
errors, writes, downloads, checks, page_previews = [], [], [], [], []

def reply(route, data):
    route.fulfill(status=200, content_type='application/json', body=json.dumps({'code': 'ok', 'data': data}, ensure_ascii=False))
def handle(route):
    req = route.request
    path = urlparse(req.url).path.removeprefix('/api/v1/')
    if req.method != 'GET':
        writes.append(path); route.abort(); return
    if path == 'users/me':
        reply(route, {'id':'expert', 'org_id':'fixture-org', 'role':'expert', 'username':'expert', 'is_active':True, 'effective_permissions':['quality', 'quality_material_read_business', 'quality_material_submit']}); return
    if path == 'runtime-context':
        reply(route, {'execution_mode':'business', 'label':'业务环境'}); return
    if path == 'quality-data/records':
        reply(route, {'items':records, 'total':2, 'page':1, 'size':20}); return
    if path == 'quality-data/reference-options':
        reply(route, {'categories':[], 'products':[], 'enterprises':[]}); return
    if path.endswith('/context') and path.startswith('quality-data/records/'):
        item = next(item for item in records if item['id'] == path.split('/')[2])
        attachment = pdf_file if item['id'] == report['local_record_id'] else txt_file
        reply(route, {'record':item, 'objects':{key:{'id':None, 'name':None, 'status':'unlinked'} for key in ['enterprise','product','category']}, 'source':{'id':'public', 'name':'人工资料接入', 'status':'active'}, 'attachments':[attachment], 'unavailable_attachment_ids':[], 'related_cases':[]}); return
    if path.endswith('/download'):
        downloads.append(path)
        route.fulfill(status=200, content_type='application/pdf' if 'public-report' in path else 'text/plain', body=pdf if 'public-report' in path else txt); return
    if '/pages/' in path and path.endswith('/preview'):
        page_previews.append(path)
        number = int(path.split('/')[-2])
        image = (SOURCES / f'sources/report-page-{number}.png').read_bytes()
        route.fulfill(status=200, content_type='image/png', body=image, headers={'X-Pdf-Page-Count':'8', 'X-Original-Sha256':pdf_file['sha256']}); return
    reply(route, [])

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, channel='chromium')
    context = browser.new_context(viewport={'width':1600, 'height':1000})
    auth = {'piap_token':'isolated-readonly-fixture','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'expert','piap_org_id':'fixture-org','piap_username':'expert'}
    context.add_init_script('if(window===window.top && location.protocol==="http:")for(const[k,v]of Object.entries('+json.dumps(auth)+'))sessionStorage.setItem(k,v)')
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/api/v1/**', handle)
    def open_record(record_id):
        page.goto('http://127.0.0.1:5173/app/quality-data?record='+record_id, wait_until='networkidle')
        expect(page.locator('.quality-record-detail')).to_be_visible()
    open_record(report['local_record_id'])
    drawer = page.locator('.quality-record-detail')
    expect(drawer.get_by_role('region', name='资料原文入口')).to_contain_text('PDF 原件 · 1 份')
    expect(drawer.get_by_role('button', name='查看原文PDF', exact=True)).to_be_visible()
    assert downloads == [], 'The narrow sidebar should not download full originals until opened'
    for width in [1600, 1280, 1024, 768, 390]:
        page.set_viewport_size({'width':width, 'height':1000})
        expected_width = min(560, width*.92)+1
        page.wait_for_function('(limit)=>document.querySelector(".quality-record-detail").getBoundingClientRect().width <= limit', arg=expected_width)
        assert drawer.bounding_box()['width'] <= expected_width, (width,drawer.bounding_box())
        assert drawer.evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), width
        checks.append({'width':width,'narrow_sidebar':True,'retains_list_context':width>=1024})
        if width == 1600: page.screenshot(path=str(OUT/'report-sidebar-1600.png'), full_page=True, animations='disabled')
    page.set_viewport_size({'width':1600, 'height':1000})
    drawer.get_by_role('button',name='查看原文PDF',exact=True).click()
    comparison = page.locator('.quality-record-comparison')
    expect(comparison).to_be_visible()
    panel = comparison.get_by_role('region', name='原件与出处对照')
    original_link = panel.get_by_role('link', name='新窗口查看原件')
    expect(original_link).to_have_attribute('href', re.compile(r'^blob:'))
    blob_hash = original_link.evaluate("""async link => {
      const buffer = await (await fetch(link.href)).arrayBuffer();
      return [...new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))].map(v=>v.toString(16).padStart(2,'0')).join('');
    }""")
    assert blob_hash == pdf_file['sha256'], 'Preview must use the exact original PDF bytes'
    frame = panel.locator('iframe[title="资料原始PDF（连续阅读）"]')
    expect(frame).to_be_visible()
    expect(frame).to_have_attribute('src',re.compile(r'^blob:.*#view=FitH'))
    expect(panel.get_by_role('spinbutton')).to_have_count(0)
    # Chromium's actual PDF viewer must load, not just an empty iframe.
    viewer = None
    for _ in range(100):
        for candidate in page.frames:
            if candidate.evaluate('!!document.querySelector("pdf-viewer")'):
                viewer = candidate; break
        if viewer: break
        page.wait_for_timeout(100)
    assert viewer is not None, 'Native PDF viewer did not initialize'
    for _ in range(100):
        if viewer.evaluate('() => document.querySelector("pdf-viewer").documentDimensions?.pageDimensions?.length === 8'): break
        page.wait_for_timeout(100)
    box = frame.bounding_box()
    page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
    for _ in range(100):
        if viewer.evaluate('() => document.querySelector("pdf-viewer").viewport_?.getMostVisiblePage() === 7'): break
        page.mouse.wheel(0,50000)
        page.wait_for_timeout(100)
    scroll_result = viewer.evaluate('() => ({page:document.querySelector("pdf-viewer").viewport_.getMostVisiblePage(),pages:document.querySelector("pdf-viewer").documentDimensions.pageDimensions.length})')
    assert scroll_result == {'page':7,'pages':8}, scroll_result
    page.mouse.wheel(0,-50000)
    for _ in range(100):
        if viewer.evaluate('() => document.querySelector("pdf-viewer").viewport_.getMostVisiblePage() === 0'): break
        page.wait_for_timeout(50)
    assert page_previews == [], 'Continuous reading must not request server-rendered page images'
    assert downloads.count('quality-data/attachments/public-report/download') == 1
    expect(comparison.get_by_role('region', name='对照资料记录')).to_contain_text('30.8')
    readings = comparison.get_by_role('region',name='逐项数值对照')
    expect(readings.locator('article')).to_have_count(3)
    expect(readings).to_contain_text('51.4')
    expect(readings).to_contain_text('73')
    assert not comparison.locator('.comparison-summary').evaluate('(element)=>element.open')
    expect(comparison.locator('.comparison-summary .comparison-saved-text')).not_to_be_visible()
    def check_page_jump(number):
        comparison.get_by_role('button',name=f'对照原 PDF 第{number}页',exact=True).first.click()
        expect(frame).to_have_attribute('src',re.compile(f'#page={number}&view=FitH'))
        found = False
        for _ in range(150):
            for candidate in page.frames:
                try:
                    current = candidate.evaluate('() => document.querySelector("pdf-viewer")?.viewport_?.getMostVisiblePage()')
                    if current == number-1: found=True;break
                except Exception:
                    continue # Chromium replaces its extension frame during navigation.
            if found: break
            page.wait_for_timeout(100)
        assert found, f'The source link must open original PDF page {number}'
    check_page_jump(5)
    check_page_jump(3)
    page.wait_for_timeout(350) # Native PDF content paints in a separate Chromium compositor.
    assert downloads.count('quality-data/attachments/public-report/download') == 1, 'Field navigation must reuse the already downloaded original'
    for width in [1600, 1280, 1024, 768, 390]:
        page.set_viewport_size({'width':width, 'height':1000})
        assert drawer.evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), width
        assert page.locator('.record-detail-layout').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), width
        assert comparison.evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), width
        assert comparison.locator('.record-comparison-layout').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), width
        if width >= 1280:
            assert frame.bounding_box()['height'] >= 500
            assert panel.bounding_box()['width'] > comparison.locator('.comparison-record').bounding_box()['width']*1.6
        label = page.locator('.record-metadata .el-descriptions__label').first
        assert label.bounding_box()['width'] >= 99, width
        checks.append({'width':width, 'all_fields_fit':True})
        if width in [1600, 390]:
            page.screenshot(path=str(OUT/f'report-{width}.png'), full_page=True, animations='disabled')
    page.set_viewport_size({'width':1600, 'height':1000})
    comparison.locator('.el-dialog__headerbtn').click()
    expect(comparison).not_to_be_visible()
    expect(drawer).to_be_visible()
    assert report['local_record_id'] in page.url, 'Closing comparison must preserve the selected record'
    open_record(charger['local_record_id'])
    expect(drawer.get_by_role('region',name='资料原文入口')).to_contain_text('本条没有 PDF 附件')
    expect(drawer.get_by_role('button',name='查看原文PDF',exact=True)).to_have_count(0)
    page.screenshot(path=str(OUT/'web-source-sidebar-1600.png'), full_page=True, animations='disabled')
    drawer.get_by_role('button',name='阅读原始资料',exact=True).click()
    expect(comparison).to_be_visible()
    panel = comparison.get_by_role('region',name='原件与出处对照')
    expect(panel.locator('.original-text')).to_contain_text('80批次')
    expect(panel.locator('.original-text')).not_to_contain_text('你的位置')
    expect(panel.locator('.original-text')).not_to_contain_text('索\n引\n号')
    text_original = panel.get_by_role('link',name='新窗口查看原件',exact=True)
    expect(text_original).to_have_attribute('href',re.compile(r'^blob:'))
    with page.expect_popup() as popup_info:
        text_original.click()
    text_window = popup_info.value
    text_window.wait_for_load_state('domcontentloaded')
    expect(text_window.locator('body')).to_contain_text('2024年电子产品用锂离子电池和电池组等27种产品质量国家监督抽查情况通报')
    text_original_hash = text_window.evaluate("""async()=>{
      const bytes=await (await fetch(location.href)).arrayBuffer();
      return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
    }""")
    assert text_original_hash == txt_file['sha256'], 'The new window must open the original attachment, not the formatted reading copy'
    text_window.close()
    expect(comparison).to_be_visible()
    body_start = '2024年，市场监管总局组织'
    source_body = body_start + txt.decode('utf-8').split(body_start, 1)[1]
    displayed_body = '\n'.join(panel.locator('.original-text p').all_text_contents())
    assert re.findall(r'\d+(?:\.\d+)?', displayed_body) == re.findall(r'\d+(?:\.\d+)?', source_body), 'Reading layout must retain every article numeric token in order'
    expect(panel.get_by_role('link', name='打开来源网页')).to_have_attribute('href', charger['provenance']['source_url'])
    panel.get_by_label('查找正文', exact=True).fill('电动自行车充电器')
    panel.get_by_role('button',name='查找',exact=True).click()
    panel.get_by_role('button',name='查找',exact=True).click()
    expect(panel.locator('[data-reading-match="true"]')).to_contain_text('80批次')
    assert comparison.locator('.el-dialog__body').evaluate('(el)=>el.scrollTop') == 0
    assert comparison.get_by_role('region',name='对照资料记录').bounding_box()['y'] < 250
    page.screenshot(path=str(OUT/'web-source-1600.png'), full_page=True, animations='disabled')
    panel.locator('.original-controls').screenshot(path=str(OUT/'original-window-entry.png'),animations='disabled')
    panel.get_by_text('查看文字副本原始排版', exact=True).click()
    expect(panel.locator('.original-raw-copy pre')).to_contain_text('你的位置')
    expect(comparison.locator('iframe')).to_have_count(0)
    assert not errors and not writes, {'errors':errors, 'writes':writes}
    (OUT/'checks.json').write_text(json.dumps({'checks':checks, 'exact_original_pdf_sha256':blob_hash,'continuous_scroll_last_page':scroll_result,'pdf_download_requests':1,'server_page_image_requests':len(page_previews),'text_original_new_window_sha256':text_original_hash,'pdf_and_text_original_links_available':True,'web_source_body_reading':True, 'all_article_numeric_tokens_preserved':True, 'original_text_still_available':True, 'comparison_closes_to_sidebar':True, 'errors':errors, 'business_writes':writes, 'mode':'isolated API responses, actual previously collected public files'}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()
print(json.dumps({'passed':True,'widths':5,'narrow_sidebar_and_separate_comparison':True,'pdf_bytes_verified':True,'web_source_body_reading':True,'business_writes':0}))
