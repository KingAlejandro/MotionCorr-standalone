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
