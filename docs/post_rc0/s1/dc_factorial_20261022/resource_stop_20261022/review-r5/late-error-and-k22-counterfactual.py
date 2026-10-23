# SPDX-License-Identifier: GPL-2.0-or-later
"""Data-only R5 live-root race and fixture counterfactual. No source amendment adopted."""
from pathlib import Path
import ast,importlib.util,json,os,types
from unittest.mock import patch
P=Path(__file__).resolve().parent
T=P/'exact/docs/post_rc0/s1/dc_factorial_20261022/tools'
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=load('r5_live_worker',T/'gpu_worker_v6.py')
class Root: pid=900001; returncode=None; mc_birth=17
class Table:
 def group_live(self,g):return True
 def read(self,p):return dict(pid=p,ppid=os.getpid(),pgid=900001,start=17,state='R')
class Own:
 def __init__(self,late):self.errors=[];self.table=Table();self.n=0;self.late=late
 def refresh(self):
  self.n+=1
  if self.late and self.n==2:self.errors.append('synthetic observer failed between entry and signalling')
 def known_live(self):return [self.table.read(900001)]
 def verified_group(self,g):return True
result={}
with patch.object(M.subprocess,'Popen',side_effect=AssertionError('forbidden Popen')),patch.object(M.os,'kill',side_effect=AssertionError('forbidden kill')),patch.object(M.signal,'signal',side_effect=AssertionError('forbidden handler')):
 for late in [False,True]:
  own=Own(late)
  with patch.object(M,'signal_job_group') as fallback,patch.object(M.os,'killpg') as group:
   signals,errors=M.terminate_owned(own,Root(),0)
  result['live_root_late_error' if late else 'live_root_healthy']={'signals':signals,'errors':errors,'fallback_calls':fallback.call_count,'group_calls':group.call_count,'refresh_calls':own.n}
 # Counterfactual fixture change only in memory: the original exact blob is unchanged.
 source=(T/'test_gpu_worker_v6.py').read_text(); tree=ast.parse(source)
 k22=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='k22')
 root=next(n for n in k22.body if isinstance(n,ast.ClassDef) and n.name=='Root')
 root.body.insert(0,ast.Assign(targets=[ast.Name(id='returncode',ctx=ast.Store())],value=ast.Constant(value=0)))
 ast.fix_missing_locations(tree)
 ns={'__name__':'r5_counterfactual_not_main','__file__':str(T/'test_gpu_worker_v6.py')}
 with patch.object(M.os,'killpg',side_effect=AssertionError('forbidden actual group signal')):
  exec(compile(tree,'<in-memory K22 returncode fixture counterfactual>','exec'),ns)
  ok,detail=ns['k22'](T/'gpu_worker_v6.py')
 result['K22_fixture_only_counterfactual']={'result':'PASS' if ok else 'FAIL','detail':detail,'change':'in-memory fake Root.returncode=0 only; no author file changed'}
(P/'late-error-and-k22-counterfactual.json').write_text(json.dumps(result,indent=2)+chr(10))
print(json.dumps(result,indent=2))
