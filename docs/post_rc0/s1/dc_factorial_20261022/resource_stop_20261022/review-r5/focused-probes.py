# SPDX-License-Identifier: GPL-2.0-or-later
"""R5 exact-source data-only reproductions; no worker/mock/query/process signalling."""
import importlib.util,json,os,sys,traceback,time
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parent
T=P/'exact/docs/post_rc0/s1/dc_factorial_20261022/tools'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
H=load('r5_harness',T/'test_gpu_worker_v6.py')
W=T/'gpu_worker_v6.py'
result={'scope':'data only; Popen, kill/killpg and signal handler installation forbidden; no process qualification','time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
with patch.object(H.subprocess,'Popen',side_effect=AssertionError('forbidden Popen')), patch.object(H.os,'kill',side_effect=AssertionError('forbidden kill')), patch.object(H.os,'killpg',side_effect=AssertionError('forbidden killpg')), patch.object(H.signal,'signal',side_effect=AssertionError('forbidden handler installation')):
 result['K28_K30']=H.r3_controls(W,['K28','K30'])
 try:
  result['K22_original']=H.k22(W)
 except Exception as e:
  result['K22_original']={'result':'FAIL','exception':repr(e),'trace':traceback.format_exc()}
 M=load('r5_worker',W)
 class Root:
  pid=900001; returncode=None; mc_birth=17
 class Table:
  def group_live(self,g):return True
  def read(self,pid):return {'pid':pid,'pgid':pid,'ppid':os.getpid(),'start':17,'state':'Z'}
 class Own:
  def __init__(self,late):self.errors=[];self.table=Table();self.n=0;self.late=late
  def refresh(self):
   self.n+=1
   if self.late and self.n==2:self.errors.append('synthetic observer failure after first refresh')
  def known_live(self):return []
  def verified_group(self,g):return True
 for late in [False,True]:
  own=Own(late)
  with patch.object(M,'signal_job_group') as fallback,patch.object(M.os,'killpg') as group:
   signals,errors=M.terminate_owned(own,Root(),0)
  result['late_observer_error' if late else 'healthy_control']={'signals':signals,'errors':errors,'fallback_calls':fallback.call_count,'group_calls':group.call_count,'refresh_calls':own.n}
(P/'focused-probes.json').write_text(json.dumps(result,indent=2,default=str)+'
')
print(json.dumps(result,indent=2,default=str))
