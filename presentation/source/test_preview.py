import asyncio,json,pathlib
from playwright.async_api import async_playwright
R=pathlib.Path(__file__).resolve().parents[1]
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
  page=await browser.new_page(viewport={'width':1440,'height':920})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.set_content((R/'preview.html').read_text(),wait_until='load');await page.evaluate('document.fonts.ready')
  await page.click('#review-play');await page.wait_for_timeout(800);await page.click('#review-play')
  time1=await page.locator('#review-time').inner_text()
  await page.evaluate("()=>{const s=document.getElementById('review-seek');s.value=130;s.dispatchEvent(new Event('input'));}")
  time2=await page.locator('#review-time').inner_text()
  await page.screenshot(path=str(R/'review/preview-player.jpg'),type='jpeg',quality=90)
  audio=await page.evaluate("()=>{const a=document.getElementById('score');return {duration:a.duration,currentTime:a.currentTime,readyState:a.readyState,paused:a.paused,error:a.error?.message||null};}")
  await page.uncheck('#captions-toggle')
  captions=await page.evaluate("getComputedStyle(document.querySelector('.caption-box')).opacity")
  result={'errors':errors,'play_pause_clock':time1,'seek_clock':time2,'audio':audio,'hidden_caption_opacity':captions}
  print(json.dumps(result,indent=2));(R/'review/player-test.json').write_text(json.dumps(result,indent=2))
  await browser.close()
asyncio.run(main())
