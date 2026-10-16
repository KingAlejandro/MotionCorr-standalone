#!/usr/bin/env python3
"""Make a portable, offline review player with no bundled fonts."""
from pathlib import Path
from render_helpers import inline_composition
ROOT=Path(__file__).resolve().parents[1]
html=inline_composition(ROOT).replace('<meta name="viewport" content="width=1920">','<meta name="viewport" content="width=device-width,initial-scale=1">')
extra=r'''
<style>
html,body{width:100%;height:100%;overflow:hidden;background:#090E16}
#film{position:absolute;left:50%;top:calc((100% - 86px)/2);width:1920px;height:1080px;transform:translate(-50%,-50%) scale(var(--preview-scale,.5));transform-origin:center}
#review-controls{position:fixed;bottom:0;left:0;right:0;z-index:1000;height:78px;background:#111722;border-top:1px solid #35425A;display:flex;align-items:center;gap:14px;padding:12px 22px;font:14px Arial,sans-serif;color:#F5F2EB}
#review-controls button,.voice-label{border:1px solid #526581;border-radius:7px;background:#1B2B43;color:#F5F2EB;padding:11px 14px;cursor:pointer;font:14px Arial,sans-serif;white-space:nowrap}
#review-controls button:hover,.voice-label:hover{background:#2D4567}
#review-controls input[type=range]{flex:1;min-width:60px;accent-color:#A8C7FA}
#review-time{font:14px monospace;white-space:nowrap;min-width:100px}
#caption-label{display:flex;gap:5px;align-items:center;white-space:nowrap}
#voice-file{display:none}
#voice-state{position:fixed;bottom:81px;right:20px;z-index:1000;font:11px Arial,sans-serif;color:#99A6BA;opacity:.8}
@media(max-width:700px){#review-controls{gap:7px;padding:8px;height:66px}#review-controls button,.voice-label{padding:9px;font-size:12px}.voice-label,#voice-state,#caption-label{display:none}#review-time{font-size:12px;min-width:87px}}
</style>
<div id="review-controls">
<button id="review-play" title="Space to play or pause">Play</button>
<span id="review-time">00:00 / 03:00</span>
<input id="review-seek" aria-label="Seek video" type="range" min="0" max="180" step="0.01" value="0">
<label id="caption-label"><input id="captions-toggle" type="checkbox" checked> Captions</label>
<label class="voice-label" for="voice-file">Load voiceover<input id="voice-file" type="file" accept="audio/*"></label>
<button id="review-full">Fullscreen</button>
</div>
<div id="voice-state">Original instrumental score. No voiceover loaded.</div>
<script>
(()=>{
 const btn=document.getElementById('review-play'),slider=document.getElementById('review-seek');
 const score=document.getElementById('score');
 let voice=null,voiceURL=null,playing=false,t=0,last=null;
 function size(){document.documentElement.style.setProperty('--preview-scale',Math.min(innerWidth/1920,(innerHeight-86)/1080));}
 addEventListener('resize',size);size();
 function clock(x){return String(Math.floor(x/60)).padStart(2,'0')+':'+String(Math.floor(x%60)).padStart(2,'0');}
 function draw(){window.seekFilm(t);slider.value=t;document.getElementById('review-time').textContent=clock(t)+' / 03:00';}
 function sync(force){for(const a of [score,voice])if(a){if(force||Math.abs(a.currentTime-t)>.3)a.currentTime=t;}}
 function stop(){playing=false;btn.textContent=t>=179.95?'Replay':'Play';for(const a of [score,voice])if(a)a.pause();}
 async function play(){if(t>=179.95)t=0;playing=true;last=null;btn.textContent='Pause';sync(true);for(const a of [score,voice])if(a){a.play().catch(()=>{});}}
 btn.onclick=()=>playing?stop():play();
 slider.oninput=()=>{t=Number(slider.value);sync(true);draw();};
 document.getElementById('captions-toggle').onchange=e=>{document.querySelector('.caption-box').style.opacity=e.target.checked?'1':'0';};
 document.getElementById('review-full').onclick=()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();
 document.getElementById('voice-file').onchange=e=>{
  const f=e.target.files[0];if(!f)return;
  if(voice){voice.pause();URL.revokeObjectURL(voiceURL);}
  voiceURL=URL.createObjectURL(f);voice=new Audio(voiceURL);voice.volume=1;
  if(score)score.volume=.38;
  document.getElementById('voice-state').textContent='Local voiceover: '+f.name+' | starts at 00:00';
  voice.addEventListener('loadedmetadata',()=>{sync(true);if(playing)voice.play().catch(()=>{});},{once:true});
 };
 addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;if(e.code==='Space'){e.preventDefault();playing?stop():play();}if(e.code==='ArrowRight'){t=Math.min(179.99,t+5);sync(true);draw();}if(e.code==='ArrowLeft'){t=Math.max(0,t-5);sync(true);draw();}});
 function tick(ms){if(playing){if(last!==null)t=Math.min(179.999,t+(ms-last)/1000);draw();sync(false);if(t>=179.999)stop();}last=ms;requestAnimationFrame(tick);}
 if(score)score.volume=.9;
 draw();requestAnimationFrame(tick);
})();
</script>
'''
html=html.replace('</body>',extra+'</body>')
(ROOT/'preview.html').write_text(html)
print('Wrote',ROOT/'preview.html', (ROOT/'preview.html').stat().st_size)
