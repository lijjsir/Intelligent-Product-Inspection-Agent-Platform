"""Render the standalone UI and check navigation, document reading and responsive fit."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright, expect

folder = Path(__file__).resolve().parent
out = folder / 'renders'
out.mkdir(exist_ok=True)
errors, requests, checks = [], [], []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1600, 'height': 1100}, device_scale_factor=1)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda req: requests.append({'url': req.url, 'method': req.method}))
    for view, name in [('intake', '01-intake'), ('detail', '02-source-detail'), ('risk', '03-risk-assessment')]:
        page.goto(folder.joinpath('index.html').as_uri() + '#' + view, wait_until='networkidle')
        page.evaluate('document.fonts.ready')
        expect(page.locator('h1')).to_be_visible()
        if view == 'detail':
            expect(page.locator('#original-page')).to_be_visible()
            assert page.locator('#original-page').evaluate('(e) => e.complete && e.naturalWidth > 0')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), view
        page.screenshot(path=str(out / (name + '.png')), full_page=True)
        checks.append({'view': view, 'width': 1600, 'no_horizontal_overflow': True})

    page.goto(folder.joinpath('index.html').as_uri() + '#intake', wait_until='networkidle')
    expect(page.locator('#record-rows tr')).to_have_count(5)
    page.get_by_role('tab', name='投诉').click()
    expect(page.locator('#record-empty')).to_be_visible()
    expect(page.locator('#record-rows tr')).to_have_count(0)
    page.get_by_role('tab', name='全部资料').click()
    page.get_by_label('搜索资料', exact=True).fill('鸣号')
    page.get_by_role('button', name='查询', exact=True).click()
    expect(page.locator('#record-rows tr')).to_have_count(2)
    page.get_by_label('搜索资料', exact=True).fill('')
    page.get_by_role('button', name='查询', exact=True).click()
    page.get_by_role('button', name='速珂 TDR009Z-2Z 检验报告', exact=True).click()
    expect(page.locator('h1')).to_have_text('速珂 TDR009Z-2Z 检验报告')
    page.get_by_label('原始PDF页码').select_option('5')
    expect(page.locator('#original-page')).to_have_attribute('src', 'assets/report-page-5.png')
    page.get_by_role('button', name='放大原报告页面').click()
    expect(page.locator('#image-dialog')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#image-dialog')).not_to_be_visible()
    page.get_by_text('查看完整资料内容与来源说明', exact=True).click()
    expect(page.locator('.raw-text')).to_contain_text('三次鸣号原始读数')

    page.goto(folder.joinpath('index.html').as_uri() + '#risk', wait_until='networkidle')
    page.get_by_role('tab', name='待补充证据').click()
    expect(page.locator('#case-rows tr')).to_have_count(2)
    page.locator('#case-rows tr').first.get_by_role('button', name='补充资料', exact=True).click()
    expect(page.locator('#selected-risk')).to_contain_text('下一步：补充可核验的原始资料')
    workflow_tabs = page.get_by_role('tablist', name='研判事项详情功能')
    expect(workflow_tabs.get_by_role('tab')).to_have_count(5)
    workflow_tabs.get_by_role('tab', name='原始资料').click()
    expect(page.locator('#detail-workflow-content')).to_contain_text('80批次')
    workflow_tabs.get_by_role('tab', name='复盘报告', exact=True).click()
    expect(page.locator('#detail-workflow-content')).to_contain_text('当前不能生成正式复盘报告')
    workflow_tabs.get_by_role('tab', name='研判结论', exact=True).click()
    page.locator('#selected-risk').screenshot(path=str(out / '04-risk-detail-current-flow.png'))
    page.get_by_role('tab', name='全部事项').click()
    page.locator('#case-rows tr').first.get_by_role('button', name='查看研判', exact=True).click()
    expect(page.locator('#selected-risk')).to_contain_text('本版未重新调用模型')
    checks.append({'interactions': ['source tabs', 'search original text', 'original PDF page switch', 'image enlargement and Escape', 'full source text', 'case state filter', 'case detail selection'], 'passed': True})

    # Reset state before mobile snapshots.
    page.reload(wait_until='networkidle')
    for width in [1440, 1280, 1024, 768, 390]:
        page.set_viewport_size({'width': width, 'height': 1000})
        for view in ['intake', 'detail', 'risk']:
            page.goto(folder.joinpath('index.html').as_uri() + '#' + view, wait_until='networkidle')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (view, width)
            if view in ['intake', 'risk']:
                # Every record retains every field, including on card layouts.
                hidden = page.locator('tbody td').evaluate_all('(cells) => cells.filter(e => getComputedStyle(e).display === "none").length')
                assert hidden == 0, (view, width, 'hidden fields')
                overflow = page.locator('tbody td').evaluate_all('(cells) => cells.filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.innerText)')
                assert not overflow, (view, width, overflow)
            checks.append({'view': view, 'width': width, 'no_horizontal_overflow': True})
            if width == 390:
                page.screenshot(path=str(out / (view + '-mobile.png')), full_page=True)
    browser.close()

assert not errors, errors
assert all(request['url'].startswith('file:') and request['method'] == 'GET' for request in requests), 'Unexpected network or write request'
report = {'checks': checks, 'browser_errors': errors, 'network_api_requests': 0, 'database_writes': 0, 'rendered_from': 'standalone HTML/CSS/JS; local public originals'}
(out / 'checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'screenshots': 7, 'layout_checks': 18, 'interaction_checks': 'passed', 'api_requests': 0, 'database_writes': 0}, ensure_ascii=False))
