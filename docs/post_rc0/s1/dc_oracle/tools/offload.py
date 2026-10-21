"""Run on 4GPUs with forwarded SSH auth. Retain bulk products in designated scratch.
For each fully completed CPU movie: copy, verify every file SHA, then remove only
that task's transferred movie copy and MRC output copies from cpu64. Originals
and complete results stay on 4GPUs. Metadata stays on both hosts.
"""
import hashlib,json,pathlib,subprocess,time,shlex
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-dc-oracle');dest=s/'cpu64';dest.mkdir(exist_ok=True)
host='ubuntu@130.246.81.24';remote='/tmp/alex-motioncorr-dc-oracle'
def ssh(code):return subprocess.check_output(['ssh','-o','BatchMode=yes',host,'python3 -c '+shlex.quote(code)],text=True)
movies=[f'{fam}-{i:02d}' for fam in ['e10216','e12963','e10474f3'] for i in range(10)]
for movie in movies:
 labels=[f'{movie}-p{g}-{a}' for g in [5,3] for a in ['R','Rprime','C_none','C_global','C_local','C_both']]
 done=dest/(movie+'-verified.json')
 if done.exists():continue
 while True:
  code=f"import json,pathlib; s=pathlib.Path({remote!r}); p=[s/'runs'/l/'run.json' for l in {labels!r}]; print(int(all(x.exists() and json.load(open(x))['rc']==0 for x in p)))"
  if ssh(code).strip()=='1':break
  time.sleep(30)
 code=f"""import json,pathlib,hashlib
s=pathlib.Path({remote!r});out={{}}
for label in {labels!r}:
 for p in (s/'runs'/label).rglob('*'):
  if p.is_file():
   h=hashlib.sha256()
   with p.open('rb') as f:
    for b in iter(lambda:f.read(4<<20),b''):h.update(b)
   out[str(p.relative_to(s))]=h.hexdigest()
print(json.dumps(out))"""
 manifest=json.loads(ssh(code))
 cmd=['ssh','-o','BatchMode=yes',host,'tar -cf - -C '+remote+' '+' '.join('runs/'+l for l in labels)]
 with subprocess.Popen(cmd,stdout=subprocess.PIPE) as a:
  b=subprocess.run(['tar','-xf','-','-C',str(dest)],stdin=a.stdout);a.stdout.close();rc=a.wait()
  assert b.returncode==rc==0,(b.returncode,rc)
 for name,want in manifest.items():
  h=hashlib.sha256()
  with (dest/name).open('rb') as f:
   for b in iter(lambda:f.read(4<<20),b''):h.update(b)
  assert h.hexdigest()==want,name
 json.dump(manifest,open(done,'w'),indent=1)
 # The transferred input copy and MRC output copies are now redundant. Keep
 # their hashes and small native records; never remove the source corpus.
 code=f"""import pathlib,json
s=pathlib.Path({remote!r});d=s/'inputs'/{movie!r};t=(d/'movies.star').read_text();movie=d/next(l.split()[0] for l in t.splitlines() if l.startswith('Movies/'));movie.unlink()
for label in {labels!r}:
 for p in (s/'runs'/label/'Movies').glob('*.mrc'):p.unlink()
(d/'OFFLOADED').write_text({str(done)!r})
print('offloaded {movie}')"""
 print(ssh(code).strip(),flush=True)
print('ALL 30 MOVIES OFFLOADED',flush=True)
