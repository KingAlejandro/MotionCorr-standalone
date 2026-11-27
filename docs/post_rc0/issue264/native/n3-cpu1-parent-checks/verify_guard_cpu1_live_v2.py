"""Independent parent live-tree admission check implementing R4 option 2."""
import ast,hashlib,json,subprocess
from pathlib import Path
W='/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-96f54dde';REV='3751bd05a95412dff468557141f2e7e01ad21831';BASE='3691374061f782bc84531fd1c79d017ddcb5a7c2';P='docs/post_rc0/issue264/native/'
blob=lambda p:subprocess.check_output(['git','-C',W,'show',REV+':'+p])
mod=ast.parse(blob(P+'n3-cpu1/check_sources.py'))
env={'SHA':REV,'BASE':BASE};cfg={}
for n in mod.body:
 if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ['EXPECT','FILES']:
  cfg[n.targets[0].id]=eval(compile(ast.Expression(n.value),'<committed frozen literals>','eval'),{'__builtins__':{}},env)
paths=subprocess.check_output(['git','-C',W,'ls-tree','-r','--name-only',REV,P+'n3-cpu1',P+'tools'],text=True).splitlines()
cfg['TOOLS']={p:hashlib.sha256(blob(p)).hexdigest() for p in paths if p.endswith(('.py','.sh','.json')) or p.endswith('FROZEN-CPU1.md')}
remote=r'''
import json,subprocess,hashlib,time,fcntl,os,shutil
from pathlib import Path
C=CONFIG
S=Path('/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(t,*a):return subprocess.check_output(['git','-C',str(S/t),*a])
r={'utc':time.strftime('%FT%TZ',time.gmtime()),'trees':{},'files':{},'locks':{},'fresh':{},'source_comparisons':{}}
status={'src-cand':[],'src-base':[],'src-ov-base':[' M src/motioncorr_runner.cpp'],'src-ov-cand':[' M src/motioncorr_runner.cpp'],'src-ov-mut':[' M src/local_motion_guard.h',' M src/motioncorr_runner.cpp']}
for t,e in C['EXPECT'].items():
 helper=S/t/'src/local_motion_guard.h'
 actual=[git(t,'rev-parse','HEAD').decode().strip(),hashlib.sha256(git(t,'diff')).hexdigest(),sha(S/t/'src/motioncorr_runner.cpp'),sha(helper) if helper.exists() else 'absent']
 st=git(t,'status','--porcelain').decode().splitlines()
 r['trees'][t]={'HEAD_diff_runner_helper':actual,'status':st,'expected':e,'match':actual==list(e) and sorted(st)==sorted(status[t])}
for p,h in {**C['FILES'],**C['TOOLS']}.items():r['files'][p]={'actual':sha(S/'src-cand'/p),'expected':h}
for ref,paths in [('52affe31f0299723faf6966d14e7516ae8e5e9bc',['src','tests','tools','CMakeLists.txt']),('4b0e4e736884777ca738c7865a37876a5e9b9e86',['src'])]:
 r['source_comparisons'][ref]=subprocess.run(['git','-C',str(S/'src-cand'),'diff','--quiet',ref,'--',*paths]).returncode
for p in ['/tmp/motioncorr-guard264-cpu14-15.lock','/tmp/motioncorr-i61-cpu-14-15.lock','/tmp/motioncorr-build.lock']:
 with open(p,'a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);r['locks'][p]=True
  except BlockingIOError:r['locks'][p]=False
def ticks():return {int(l.split()[0][3:]):list(map(int,l.split()[1:])) for l in Path('/proc/stat').read_text().splitlines() if l.startswith(('cpu14 ','cpu15 '))}
a=ticks();time.sleep(3);b=ticks();r['cpu_busy_3sec']={str(c):1-(b[c][3]+b[c][4]-a[c][3]-a[c][4])/(sum(b[c])-sum(a[c])) for c in a}
r['unexpected_paths']=[str(p.relative_to(S)) for pattern in ['build-*','n3-*','logs/cpu1-*','logs/CHAIN*','logs/cpu1.launch*'] for p in S.glob(pattern)]
r['scratch_kib']=int(subprocess.check_output(['du','-sk',str(S)],text=True).split()[0]);r['disk_free_bytes']=shutil.disk_usage(S).free
r['pbzip2_sha256']=sha(Path('/mnt/clathrin/alex-motioncorr-214/tools/usr/bin/pbzip2'))
r['fixture_sha256']=sha(Path('/mnt/clathrin/alex-motioncorr-peakfit/known-motion-cpu-fixtures/km_local_nonsquare.mrcs'))
r['bundle_sha256']=sha(S/'g264-3751bd05.bundle') if (S/'g264-3751bd05.bundle').exists() else None
r['aggregate']='Metadata admission only; no build/native/GPU performed'
print(json.dumps(r))
'''.replace('CONFIG',repr(cfg),1)
p=Path('/tmp/motioncorr-orchestrator-20261022');(p/'guard-cpu1-parent-live-v2-remote.py').write_text(remote)
r=subprocess.run(['ssh','-J','ccp4-gateway','-oBatchMode=yes','-oConnectTimeout=10','-oConnectionAttempts=1','4GPUs','taskset','-c','14-15','/home/alex/.mc-venv/bin/python3','-'],input=remote,text=True,capture_output=True,timeout=40)
(p/'guard-cpu1-parent-live-v2.stderr').write_text(r.stderr);assert r.returncode==0,(r.returncode,r.stderr)
(p/'guard-cpu1-parent-live-v2.json').write_text(r.stdout);j=json.loads(r.stdout)
assert all(v['match'] for v in j['trees'].values()),j['trees']
assert all(v['actual']==v['expected'] for v in j['files'].values())
assert not any(j['source_comparisons'].values()) and all(j['locks'].values())
assert max(j['cpu_busy_3sec'].values())<.5 and not j['unexpected_paths']
assert j['scratch_kib']<8*(1<<20) and j['disk_free_bytes']>10*(1<<30)
assert j['pbzip2_sha256']=='35410d199baebff55262e43cac9e8cdf9d14b540143c8e70ee53c6cf8ca9f21e'
assert j['fixture_sha256']=='644274e0d869d3c468db873ab2af48fc064cbf78c02f5c080d6e669907493fb3'
print(json.dumps({'status':'PASS','utc':j['utc'],'live_trees':5,'git_bound_tool_hashes':len(j['files']),'cpu_busy_3sec':j['cpu_busy_3sec'],'leases_free':True,'unexpected_paths':j['unexpected_paths'],'scratch_kib':j['scratch_kib'],'readback_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'remaining':'ONE CPU-only launch after parentGO; build-log live bindings, 21env receipts and3distinct buildbinaryhashes mandatory post-run;16CUDArowsUNRUN'}))
