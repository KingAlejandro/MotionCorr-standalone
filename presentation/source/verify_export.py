#!/usr/bin/env python3
"""Check the delivered movie, subtitle timing, representative frames and packaging."""
from pathlib import Path
import concurrent.futures
import json
import subprocess
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
VIDEO=Path('/mnt/data/Motion_Corrected_STFC_Hackathon.mp4')
# An optional command-line path makes this checker reusable outside the authoring host.
import sys
if len(sys.argv)>1:VIDEO=Path(sys.argv[1]).resolve()
story=json.loads((ROOT/'source/story.json').read_text())
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate,nb_frames,sample_rate,channels,duration','-of','json',str(VIDEO)]))
video=next(s for s in probe['streams'] if s['codec_type']=='video')
audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert video['width']==1920 and video['height']==1080
assert video['r_frame_rate']=='30/1' and int(video['nb_frames'])==5400
assert abs(float(probe['format']['duration'])-180)<.001
assert audio['channels']==2 and abs(float(audio['duration'])-180)<.01
cues=[c for s in story['scenes'] for c in s['cues']]
assert all(0<=a<b<=180 for a,b,t in cues)
assert all(cues[i][1]<=cues[i+1][0] for i in range(len(cues)-1))
assert not list(ROOT.rglob('*.ttf'))+list(ROOT.rglob('*.otf'))+list(ROOT.rglob('*.woff'))+list(ROOT.rglob('*.woff2'))
render_review=ROOT/'review/export-frames';render_review.mkdir(exist_ok=True)

def frame(i_s):
 i,s=i_s;t=min(s['end']-.7,s['start']+8)
 dest=render_review/f'{i:02d}.jpg'
 subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-threads','1','-ss',str(t),'-i',str(VIDEO),'-frames:v','1','-q:v','2',str(dest)],check=True)
 return i,dest
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 results=list(ex.map(frame,enumerate(story['scenes'])))
sheet=Image.new('RGB',(1788,1820),'#202734')
for i,path in results:
 im=Image.open(path).resize((576,324))
 tile=Image.new('RGB',(596,364),'#202734');tile.paste(im,(10,30))
 ImageDraw.Draw(tile).text((10,10),f'{i+1:02d} / encoded MP4 / {story["scenes"][i]["title"]}',fill='#F5F2EB')
 sheet.paste(tile,((i%3)*596,(i//3)*364))
sheet.save(ROOT/'review/encoded-contact-sheet.jpg',quality=92)
report={'export':VIDEO.name,'probe':probe,'subtitle_cues':len(cues),'narration_words':sum(len(c[2].split()) for c in cues),'subtitle_order':'pass','font_files_bundled':False,'representative_encoded_frames':len(results),'full_decode_error_log_bytes':(ROOT/'review/decode-errors.log').stat().st_size}
(ROOT/'review/export-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
