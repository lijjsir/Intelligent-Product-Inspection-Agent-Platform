"""Collaboration server-error recovery, with intercepted requests only."""
import asyncio,json
from playwright.async_api import async_playwright,expect
import remaining_pagination_browser as base

state={'fail':True};errors=[]


async def handle(route):
    path=route.request.url.split('/api/v1',1)[-1].split('?',1)[0]
    if path=='/collab/work-item-pages' and state['fail']:
        await route.fulfill(status=500,content_type='text/plain',body='Internal Server Error');return
    await base.handle(route)


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True);ctx=await browser.new_context(viewport={'width':1500,'height':1000})
        saved={'piap_token':'isolated','piap_role':'expert','piap_roles':'["expert"]','piap_user_id':'reviewer','piap_org_id':'fixture-org','piap_username':'fixture'}
        await ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(saved)+'))sessionStorage.setItem(k,v)')
        await ctx.route('**/api/v1/**',handle);page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(base.BASE+'/app/collab',wait_until='networkidle')
        await expect(page.locator('.error-state')).to_contain_text('协同工作项暂时无法加载')
        await expect(page.get_by_text('Request failed with status code 500',exact=False)).to_have_count(0)
        await expect(page.locator('.el-alert')).to_have_count(0)
        await expect(page.get_by_text('当前视图暂无工作项',exact=True)).to_have_count(0)
        state['fail']=False
        await page.get_by_role('button',name='重新加载',exact=True).click()
        await expect(page.locator('.error-state')).to_have_count(0)
        await expect(page.locator('.work-list')).to_contain_text('隔离工作项')
        await page.get_by_role('button',name='我发起的',exact=False).click()
        await expect(page.locator('.error-state')).to_have_count(0)
        await page.get_by_role('button',name='已处理',exact=False).click()
        await expect(page.locator('.error-state')).to_have_count(0)
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_function("document.querySelector('.app-sidebar').getBoundingClientRect().right<=1")
        await page.screenshot(path=str(base.OUT/'collab-500-recovered-mobile.png'))
        assert not errors,errors
        assert not base.writes,base.writes
        result={'passed':True,'mode':'intercepted API fixtures','server_error_shown_once_in_chinese':True,
            'error_not_misrepresented_as_empty_inbox':True,'reload_recovers_work_items':True,'three_views_and_mobile':True,
            'business_rows_written':False,'page_errors':errors}
        (base.OUT/'collab-500-browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False));await browser.close()


if __name__=='__main__':asyncio.run(main())
