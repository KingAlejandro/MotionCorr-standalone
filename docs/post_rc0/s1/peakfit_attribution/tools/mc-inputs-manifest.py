import pathlib,json,hashlib,os
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');sw=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1/sweep');out=[];cache={}
def digest(p):
 p=p.resolve();st=p.stat();k=(str(p),st.st_size,st.st_mtime_ns)
 if k not in cache:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(8<<20),b''):h.update(b)
  cache[k]={'path':str(p),'bytes':st.st_size,'sha256':h.hexdigest()}
 return cache[k]
for fam in ['e10216','e12963','e10474f3']:
 for i in range(10):
  mv='%s-%02d'%(fam,i);j=sw/'runs'/(mv+'-p5-F-cuda')/'run.json'
  if not j.exists():j=s/'extra/sweep/runs'/(mv+'-p5-F-cuda')/'run.json'
  d=json.load(open(j));cwd=pathlib.Path(d['cwd']);star=cwd/'movies.star';t=star.read_text();movie=next(l.split()[0] for l in t.splitlines() if l.strip().startswith('Movies/'))
  r={'movie':mv,'input_star':digest(star),'movie_file':digest(cwd/movie),'source_run_record':str(j),'argv':d['argv']}
  if '--gainref' in d['argv']:r['gain']=digest(cwd/d['argv'][d['argv'].index('--gainref')+1])
  out.append(r);print(mv,r['movie_file']['sha256'],flush=True)
json.dump(out,open(s/'input-manifest.json','w'),indent=1)
