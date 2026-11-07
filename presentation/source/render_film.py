#!/usr/bin/env python3
"""Render the local, deterministic HTML timeline to a captioned MP4.

Requires Python 3.10+, Playwright, Chromium, and FFmpeg.
No remote services are used. No font files are embedded or distributed.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
from playwright.async_api import async_playwright
from render_helpers import inline_composition

ROOT = Path(__file__).resolve().parents[1]

async def render(args: argparse.Namespace) -> None:
    story = json.loads((ROOT / 'source/story.json').read_text())
    fps = args.fps or story['fps']
    duration = args.duration or story['duration']
    total = round(duration * fps)
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    parts_dir = out.parent / (out.stem + '_segments')
    parts_dir.mkdir(exist_ok=True)
    workers = min(args.workers, total)
    chunk = math.ceil(total / workers)
    html = inline_composition(ROOT)
    chromium = args.chromium or shutil.which('chromium') or shutil.which('google-chrome')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg must be installed and available on PATH.')
    begin = time.monotonic()
    async with async_playwright() as p:
        kwargs = dict(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--force-color-profile=srgb'])
        if chromium:
            kwargs['executable_path'] = chromium
        browser = await p.chromium.launch(**kwargs)
        async def worker(w: int) -> Path:
            first, last = w * chunk, min(total, (w + 1) * chunk)
            part = parts_dir / f'part-{w:02d}.mp4'
            context = await browser.new_context(viewport={'width':story['width'],'height':story['height']}, device_scale_factor=1)
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            await page.set_content(html, wait_until='load')
            await page.evaluate('document.fonts.ready')
            await page.evaluate('Promise.all(Array.from(document.images).map(i=>i.decode().catch(()=>{})))')
            if args.clean:
                await page.add_style_tag(content='.caption-box{opacity:0 !important}')
            command = [ffmpeg,'-y','-hide_banner','-loglevel','error','-f','image2pipe','-vcodec','mjpeg',
                       '-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast',
                       '-crf',str(args.crf),'-pix_fmt','yuv420p','-threads','1','-movflags','+faststart',str(part)]
            log = open(parts_dir / f'encode-{w:02d}.log','wb')
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
            t0 = time.monotonic()
            try:
                for frame in range(first,last):
                    await page.evaluate('(t)=>window.seekFilm(t)',frame/fps)
                    data = await page.screenshot(type='jpeg',quality=93,animations='allow')
                    process.stdin.write(data)
                    if (frame-first+1)%150==0 or frame==last-1:
                        print(json.dumps({'worker':w,'done':frame-first+1,'total':last-first,
                                          'fps':round((frame-first+1)/(time.monotonic()-t0),2),
                                          'seconds_elapsed':round(time.monotonic()-begin,1)}),flush=True)
            finally:
                if process.stdin:
                    process.stdin.close()
                code = process.wait()
                log.close()
                await context.close()
            if code or errors:
                raise RuntimeError(f'Worker {w}: FFmpeg exit {code}; browser errors {errors}')
            return part
        parts = await asyncio.gather(*(worker(w) for w in range(workers)))
        await browser.close()
    concat = parts_dir / 'concat.txt'
    concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p in parts))
    subprocess.run([ffmpeg,'-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(concat),
                    '-c','copy','-movflags','+faststart',str(out)],check=True)
    print(json.dumps({'complete':str(out),'frames':total,'duration':duration,
                      'elapsed':round(time.monotonic()-begin,1)}),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',default=str(ROOT/'renders/motioncorr-picture.mp4'))
    ap.add_argument('--workers',type=int,default=3)
    ap.add_argument('--fps',type=int)
    ap.add_argument('--duration',type=float,help='Optional short test render')
    ap.add_argument('--crf',type=int,default=18)
    ap.add_argument('--chromium',help='Optional Chromium executable path')
    ap.add_argument('--clean',action='store_true',help='Hide burned-in subtitles for a clean export')
    args=ap.parse_args()
    if not 1<=args.workers<=8:
        ap.error('--workers must be between 1 and 8')
    asyncio.run(render(args))
