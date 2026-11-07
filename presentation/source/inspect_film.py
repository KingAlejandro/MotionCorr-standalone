import json, asyncio, pathlib
from render_helpers import inline_composition
from playwright.async_api import async_playwright
from PIL import Image, ImageOps, ImageDraw
root=pathlib.Path(__file__).resolve().parents[1]
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--force-color-profile=srgb'])
  page=await browser.new_page(viewport={'width':1920,'height':1080},device_scale_factor=1)
  errs=[]; page.on('pageerror',lambda e:errs.append(str(e)))
  await page.set_content(inline_composition(root), wait_until='load');await page.evaluate('document.fonts.ready');await page.wait_for_timeout(300)
  scenes=json.loads((root/'source/story.json').read_text())['scenes']; issues=[]
  for i,s in enumerate(scenes):
   t=min(s['end']-.6,s['start']+6.8)
   await page.evaluate('(t)=>window.seekFilm(t)',t)
   await page.screenshot(path=str(root/'review'/f'scene-{i:02d}.jpg'),type='jpeg',quality=90)
   result=await page.evaluate('''(id)=>{const sc=document.getElementById(id);const out=[];for(const el of sc.querySelectorAll('h1,h2,h3,p,.eyebrow,.source,.pill,.note')){const r=el.getBoundingClientRect();if(r.width===0||r.height===0)continue; const cs=getComputedStyle(el);if(+cs.opacity<.1)continue;if(r.left<50||r.right>1880||r.top<20||r.bottom>915)out.push({tag:el.className,text:el.innerText,rect:{x:r.x,y:r.y,w:r.width,h:r.height}});if(el.scrollWidth>el.clientWidth+4 && el.clientWidth>0)out.push({overflow:'width',tag:el.className,text:el.innerText,scroll:el.scrollWidth,client:el.clientWidth})}return out}''',s['id'])
   issues.extend({'scene':i,**r} for r in result)
  (root/'review/layout-report.json').write_text(json.dumps({'page_errors':errs,'issues':issues},indent=2))
  print(json.dumps({'page_errors':errs,'issues':issues},indent=2))
  await browser.close()
 ims=[]
 for i,s in enumerate(scenes):
  im=Image.open(root/'review'/f'scene-{i:02d}.jpg').resize((576,324))
  tile=Image.new('RGB',(596,364),'#202734');tile.paste(im,(10,30));d=ImageDraw.Draw(tile);d.text((10,10),f'{i+1:02d} / {s["start"]:03d}s / {s["title"]}',fill='#F5F2EB');ims.append(tile)
 sheet=Image.new('RGB',(596*3,364*5),'#202734')
 for i,im in enumerate(ims):sheet.paste(im,((i%3)*596,(i//3)*364))
 sheet.save(root/'review/contact-sheet.jpg',quality=93)
asyncio.run(main())
