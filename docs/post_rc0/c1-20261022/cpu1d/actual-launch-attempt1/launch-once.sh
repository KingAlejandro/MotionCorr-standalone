#!/bin/bash
set -euo pipefail
set -C
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb
E=$SC/cpu1d-actual-launch-attempt1
mkdir "$E"
/home/alex/.mc-venv/bin/python3 -B - "$SC" "$E" <<'PY'
import datetime,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
sc,e=map(Path,sys.argv[1:]);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':os.uname().nodename,'uid':os.getuid(),'source':{},'CPU1D_overrides':{k:v for k,v in os.environ.items() if k.startswith('CPU1D_')},'files':{},'fresh_paths':{}}
assert not r['CPU1D_overrides']
for args in [('rev-parse','HEAD'),('status','--porcelain')]:
 p=subprocess.run(['git','-C',str(sc/'src'),*args],capture_output=True,text=True,check=True);r['source'][' '.join(args)]=p.stdout
assert r['source']['rev-parse HEAD'].strip()=='e77a51a220cb0d91f4ac3c7fac211876d0c6833f' and not r['source']['status --porcelain']
expected={'chain-cpu1d.sh':'3c842fb2c505bf5db4dac37b21db6fcbc0aad1ae3ea1b083b10bba57f2958cdc','cpu1d-launch-wrapper.sh':'ac71cae5ca0696859fb48731a94c77a235b3266a6f33ee1c6e795635248df404','cpu1d-tools-expected.sha256':'8ce87b51c1121dd0e0c1a8b14b99643427e3e3ec8525dea75a4b0dc6c1a953c'}
# Manifest hash is independently bound below to the deployed freeze packet;
# source/chain/wrapper hashes are fixed explicitly, not selected from live data.
expected.pop('cpu1d-tools-expected.sha256')
for name,h in expected.items():r['files'][name]=sha(sc/name);assert r['files'][name]==h
m=json.loads((sc/'cpu1d-startup-freeze1/cpu1d-manifest.json').read_text())
r['tools']={p.name:sha(p) for p in (sc/'tools-cpu1d-run').iterdir()};assert len(r['tools'])==32 and r['tools']==m['tools_sha256']
assert (sc/'cpu1d-tools-expected.sha256').read_bytes()==(sc/'cpu1d-startup-freeze1/cpu1d-tools-expected.sha256').read_bytes()
for name,h in [('build-cpu/motioncorr','5692c6dc5eaca953357bf7a1161338b99ca320369f0b6c6ab025d9aaa7f9dc3c'),('cpu1c-identities.json',m['expected_identities']['sha256']),*[(f'cpu1c-pins/{n}',h) for n,h in m['pins'].items()],*[(f't24/F-cpu-{c}/RUN.json',m['pins'][f'F-cpu-{c}.RUN.json']) for c in 'GL']]:
 r['files'][name]=sha(sc/name);assert r['files'][name]==h
r['F_binary']=sha(Path('/mnt/clathrin/alex-motioncorr-rc0/W-QF/build-cpu/motioncorr'));assert r['F_binary']=='43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42'
r['tutorial_star']=sha(Path('/home/alex/motioncorr-validation-20261011-vm/tutorial-data/movies.star'));assert r['tutorial_star']=='fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041'
for name in ['logs/launch-cpu1d-attempt1','logs/launch-cpu1d-attempt1.outer.out','logs/chain-cpu1d.out','logs/chain-cpu1d.started','logs/chain-cpu1d.pid','logs/chain-cpu1d.cpus','t24-cpu1d','census','census-ref-cpu','v2/cpu-unset','v2/cpuF-unset']:
 r['fresh_paths'][name]=not (sc/name).exists();assert r['fresh_paths'][name]
r['stage_receipts']=[p.name for p in (sc/'logs').glob('cpu1d-*')];assert not r['stage_receipts']
r['old_pids_absent']={str(p):not Path(f'/proc/{p}').exists() for p in [3308367,3308375]};assert all(r['old_pids_absent'].values())
go=sc/'logs/chain-cpu1d.go';r['GO']={'sha256':sha(go),'mtime_ns':go.stat().st_mtime_ns,'uid':go.stat().st_uid,'content':go.read_text()};(e/'parent-GO.copy').write_bytes(go.read_bytes())
def cpu():
 return {l.split()[0]:list(map(int,l.split()[1:])) for l in Path('/proc/stat').read_text().splitlines() if l.split()[0] in ['cpu8','cpu9']}
a=cpu();time.sleep(3);b=cpu();r['cpu_busy_3sec']={}
for k in a:
 d=[y-x for x,y in zip(a[k][:8],b[k][:8])];r['cpu_busy_3sec'][k]=100*(sum(d)-d[3]-d[4])/sum(d)
assert max(r['cpu_busy_3sec'].values())<=5, 'CPU lane busy; stop before launch'
with Path('/tmp/motioncorr-c1-cpu8-9.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);r['lease_free_immediately_before_launch']=True
r['df']=subprocess.check_output(['df','-B1','/mnt/clathrin'],text=True)
(e/'preflight.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'preflight':'PASS','cpu_busy_3sec':r['cpu_busy_3sec'],'utc':r['utc']}))
PY
# Exactly one frozen default invocation. No CPU1D overrides or parameter changes.
nohup setsid taskset -c 8-9 bash /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/cpu1d-launch-wrapper.sh > /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/logs/launch-cpu1d-attempt1.outer.out 2>&1 < /dev/null &
launcher=$!
printf '%s\n' "$launcher" > "$E/launcher.pid"
date -u +%FT%TZ > "$E/launcher.returned"
printf '%s\n' 'nohup setsid taskset -c 8-9 bash /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/cpu1d-launch-wrapper.sh > /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/logs/launch-cpu1d-attempt1.outer.out 2>&1 < /dev/null &' > "$E/launch.command"
# One bounded startup delay; no loop, retry or full-chain wait.
sleep 3
printf '%s\n' 'DETACHED; reconcile wrapper/chain receipts, not launcher shell status'
