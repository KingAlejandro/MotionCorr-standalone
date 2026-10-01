#!/usr/bin/env python3
"""Actual cleanup functions and diagnostic-delta checks, no GPU required."""
import ast,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
from dose_log_contract import validate_vram_delta
src=Path(__file__).with_name('run_dose_pairs.py')
tree=ast.parse(src.read_text());functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('group_members','stop_owned_group')]
assert len(functions)==2
space={'Path':Path,'os':os,'signal':signal,'subprocess':subprocess,'time':time}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(src),'exec'),space)
members,stop=space['group_members'],space['stop_owned_group']
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp)
 for mutant in [False,True]:
  pidfile=root/('mutant.pid' if mutant else 'healthy.pid')
  code='''import os,signal,time,sys
child=os.fork()
if child==0:
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 open(sys.argv[1],'w').write(str(os.getpid()))
 time.sleep(30)
else:
 time.sleep(.25)
 os._exit(0)
'''
  proc=subprocess.Popen([sys.executable,'-c',code,str(pidfile)],start_new_session=True)
  start=int(Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()[19])
  try:
   proc.wait(timeout=5)
   assert pidfile.exists() and int(pidfile.read_text()) in members(proc.pid,start),'reparented owned child control not established'
   if mutant:
    # Previously incorrect parent-only criterion deliberately refuses escalation.
    if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL)
    assert members(proc.pid,start),'parent-only mutation failed to retain distinguishing child'
   else:
    stop(proc,start)
    assert not members(proc.pid,start),'real cleanup left reparented TERM-ignoring child'
  finally:
   stop(proc,start)
 print('PASS actual group cleanup and parent-only negative control')
 for dirname in ['b','c']:(root/dirname).mkdir()
 b,c=root/'b',root/'c';name='movie.log'
 before='[CUDA Global Alignment Profile]\n Peak VRAM: 50.00 MiB\n[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]\n Peak VRAM: 100.00 MiB\n'
 after=before.replace('100.00','100.02')
 (b/name).write_text(before);(c/name).write_text(after)
 validate_vram_delta(b,c,64,128) # Plane0.016113MiB rounds to0.02.
 bad=[after.replace('50.00','50.10'),after.replace('100.02','100.50'),after.replace('100.02','100.00'),after.replace('Resident VRAM','Other'),after+' Peak VRAM: 1.00 MiB\n']
 for text in bad:
  (c/name).write_text(text)
  try:validate_vram_delta(b,c,64,128)
  except RuntimeError:pass
  else:raise AssertionError('diagnostic delta mutation accepted')
 print('PASS numeric/stage allocation delta and5negative controls')
 # A child intentionally held as a zombie by its still-live parent.
 zombiefile=root/'zombie.pid'
 code="import os,time,sys; c=os.fork();\nif c==0: os._exit(0)\nopen(sys.argv[1],'w').write(str(c));time.sleep(30)"
 proc=subprocess.Popen([sys.executable,'-c',code,str(zombiefile)],start_new_session=True)
 start=int(Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()[19])
 try:
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   if zombiefile.exists():
    child=int(zombiefile.read_text());path=Path(f'/proc/{child}/stat')
    if path.exists() and path.read_text().rsplit(')',1)[1].split()[0]=='Z':break
   time.sleep(.01)
  else:raise AssertionError('zombie control not established')
  assert child not in members(proc.pid,start) and proc.pid in members(proc.pid,start)
  old=src.read_text().replace("stat[0]!='Z' and ",'')
  oldtree=ast.parse(old);oldspace=dict(space)
  exec(compile(ast.Module(body=[n for n in oldtree.body if isinstance(n,ast.FunctionDef) and n.name=='group_members'],type_ignores=[]),str(src),'exec'),oldspace)
  assert child in oldspace['group_members'](proc.pid,start),'old zombie criterion not discriminated'
 finally:stop(proc,start)
 print('PASS zombie exclusion and old criterion negative control')
 # Execute the actual summary CLI; no predicate reimplementation.
 import json,hashlib,shutil
 phase=root/'complete';phase.mkdir();records=[]
 for pair in range(1,3):
  for arm in ('baseline','candidate'):
   d=phase/f'{arm}-{pair}';d.mkdir();(d/'device.csv').write_text('timestamp, uuid, 40, 100\n')
   records.append({'pair':pair,'arm':arm,'whole_process_wall_seconds':2 if arm=='baseline' else 1,'directory':str(d),'resource':'Maximum resident set size (kbytes): 1024\nPercent of CPU this job got: 100%\nElapsed (wall clock) time (h:mm:ss or m:ss): 0:01\n','actual_cpu_mask':'0'})
  (phase/f'exact-{pair}.json').write_text(json.dumps({'status':'PASS'}))
 (phase/'runs.json').write_text(json.dumps(records));(phase/'provenance.json').write_text(json.dumps({'expected_pair_count':2}))
 def seal():
  digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
  (phase/'COMPLETE.json').write_text(json.dumps({'expected_pair_count':2,'runs_sha256':digest(phase/'runs.json'),'provenance_sha256':digest(phase/'provenance.json'),'exact_sha256':{str(n):digest(phase/f'exact-{n}.json') for n in (1,2)}}))
 def summary():return subprocess.run([sys.executable,str(src.with_name('summarize_campaign.py')),str(root),'--phases','complete'],capture_output=True,text=True)
 seal();assert summary().returncode==0
 original={p.name:p.read_bytes() for p in phase.iterdir() if p.is_file()}
 for mutation in ('missing-marker','prefix','missing-arm','duplicate-pair','changed-record','failed-exact'):
  for name,data in original.items():(phase/name).write_bytes(data)
  if mutation=='missing-marker':(phase/'COMPLETE.json').unlink()
  elif mutation=='prefix':(phase/'runs.json').write_text(json.dumps(records[:2]));seal()
  elif mutation=='missing-arm':(phase/'runs.json').write_text(json.dumps(records[:3]));seal()
  elif mutation=='duplicate-pair':(phase/'runs.json').write_text(json.dumps(records[:2]*2));seal()
  elif mutation=='changed-record':(phase/'runs.json').write_text(json.dumps(records)+' ')
  else:(phase/'exact-2.json').write_text(json.dumps({'status':'FAIL'}));seal()
  assert summary().returncode!=0,'actual summary accepted '+mutation
 print('PASS actual complete summary and6negative controls')
