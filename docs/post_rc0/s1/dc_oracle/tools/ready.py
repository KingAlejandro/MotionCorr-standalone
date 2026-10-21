"""Hash each transferred input once, then release that movie to CPU workers."""
import hashlib,json,pathlib,time
s=pathlib.Path('/tmp/alex-motioncorr-dc-oracle')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
manifest=json.load(open(s/'input-manifest.json'));remaining=list(manifest);records=[]
while remaining:
 for m in remaining[:]:
  d=s/'inputs'/m['movie']
  if not (d/'movies.star').exists():continue
  movie=d/next(l.split()[0] for l in (d/'movies.star').read_text().splitlines() if l.startswith('Movies/'))
  if not movie.exists() or movie.stat().st_size!=m['movie_file']['bytes']:continue
  # A stream may have allocated the final file size before all bytes arrive.
  got=sha(movie)
  if got!=m['movie_file']['sha256']:continue
  checks={'movie_sha256':got,'input_star_sha256':sha(d/'movies.star')}
  assert checks['input_star_sha256']==m['input_star']['sha256']
  if 'gain' in m:
   gain=d/m['argv'][m['argv'].index('--gainref')+1]
   if not gain.exists():continue
   checks['gain_sha256']=sha(gain);assert checks['gain_sha256']==m['gain']['sha256']
  (d/'READY').write_text(json.dumps(checks));records.append({'movie':m['movie'],**checks});remaining.remove(m)
  json.dump(records,open(s/'input-transfer-verification.json','w'),indent=1);print('READY',m['movie'],flush=True)
 if remaining:time.sleep(15)
print('ALL 30 INPUTS VERIFIED',flush=True)
