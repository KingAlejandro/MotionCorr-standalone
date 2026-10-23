# Independent R6 branch/identity probes. All PIDs and tables below are synthetic.
import importlib.util, json, os, signal, subprocess, time, types
from pathlib import Path
from unittest.mock import patch
N=Path(__file__).parent; T=N/'docs/post_rc0/s1/dc_factorial_20261022/tools'
spec=importlib.util.spec_from_file_location('r6_independent_worker',T/'gpu_worker_v6_1.py')
M=importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
def forbidden(*a,**kw): raise AssertionError('forbidden real process/signal/handler')
class Root:
    pid=910001; mc_birth=71
    def __init__(self): self.returncode=None; self.events=[]
    def poll(self): raise AssertionError('must not reap before fallback')
    def send_signal(self,s): self.events.append(['root',int(s)])
    def wait(self,timeout=None): self.events.append(['wait',timeout]); self.returncode=0
class Own:
    def __init__(self,mode):
        self.mode=mode; self.errors=[]; self.n=0; self.checked=0; self.table=self; self.rows=0
    def refresh(self): self.n+=1
    def known_live(self):
        if self.mode=='known_live' and self.n==1: self.errors.append('late during known_live')
        return [dict(pid=910001,pgid=910001,start=71)]
    def group_live(self,g):
        if self.mode=='group_live': self.errors.append('late during group_live')
        if self.mode=='group_live_raises': raise OSError('synthetic group scan failed')
        return True
    def verified_group(self,g):
        self.checked+=1
        if self.mode=='verify_raises': raise OSError('synthetic verification failed')
        if self.mode=='late_kill' and self.checked==2: self.errors.append('late at KILL verification')
        if self.mode.startswith('identity_') or self.mode=='read_raises': self.errors.append('late at verification')
        return True
    def read(self,pid):
        self.rows+=1
        if self.mode=='read_raises': raise OSError('synthetic identity unavailable')
        row=dict(pid=pid,ppid=os.getpid(),pgid=pid,start=71,state='R')
        if self.rows>=2:
            if self.mode=='identity_birth': row['start']=72
            if self.mode=='identity_parent': row['ppid']=1
            if self.mode=='identity_pgid': row['pgid']=910002
        return row
result={}
try:
    with patch.object(subprocess,'Popen',side_effect=forbidden),patch.object(os,'kill',side_effect=forbidden),patch.object(os,'killpg',side_effect=forbidden),patch.object(signal,'signal',side_effect=forbidden):
        modes=['known_live','group_live','group_live_raises','verify_raises','late_kill','after_term','identity_birth','identity_parent','identity_pgid','identity_sid','identity_own_group','identity_reaped','read_raises']
        for mode in modes:
            own=Own(mode); root=Root(); calls=[]
            def sid(pid): return 910002 if mode=='identity_sid' and own.rows>=2 else pid
            def mygroup(): return root.pid if mode=='identity_own_group' and own.rows>=2 else 810000
            def group(g,s):
                calls.append([g,int(s)])
                if mode=='after_term' and int(s)==int(signal.SIGTERM): own.errors.append('late after TERM check')
                if mode=='identity_reaped': root.returncode=0
            with patch.object(M.os,'getpgrp',side_effect=mygroup),patch.object(M.os,'getsid',side_effect=sid),patch.object(M.os,'killpg',side_effect=group),patch.object(M,'signal_job_group',wraps=M.signal_job_group) as fallback:
                signals,errors=M.terminate_owned(own,root,0)
            assert fallback.call_count==1,(mode,'must enter fallback exactly once')
            assert errors,(mode,'uncertainty must survive')
            if mode.startswith('identity_'):
                assert calls==[[root.pid,int(signal.SIGTERM)]],(mode,calls)
                if mode!='identity_reaped': assert ['root',int(signal.SIGKILL)] in root.events
            elif mode=='read_raises':
                assert not calls and root.events[:2]==[['root',15],['root',9]]
            else:
                expected=[[root.pid,15],[root.pid,9]]
                if mode in ('late_kill','after_term'): expected.insert(0,[root.pid,15])
                assert calls==expected,(mode,calls,expected)
            result[mode]=dict(result='PASS',group_calls=calls,root_events=root.events,signals=signals,errors=errors,fallback_calls=fallback.call_count)
        # A failure of the checked fallback must leave the existing main backstop holding,
        # including when receipt I/O also fails. No real lease or signal is used here.
        class Held(BaseException): pass
        for mode in ('uncertainty_outcome','exception_backstop'):
            a=M.parse(['--root',str(N),'--queue','q','--queue-sha256','x','--runs-dir',str(N/('synthetic-'+mode)),'--binaries','b','--binaries-sha256','y','--uuid','NO-GPU','--expected-jobs','1','--cpu','0','--gpu-index','2'])
            w=M.Worker(a); w.launched=1; w.job_cleanup_verified=False
            holds=[]
            def hold(*a,**kw): holds.append([a,kw]); raise Held()
            patches=[patch.object(w,'bind',return_value=([dict(id='J',build='cuda-exp')],{'cuda-exp':{}},[])),patch.object(w,'hold_lease',side_effect=hold),patch.object(M.signal,'signal',return_value=None),patch.object(M.fcntl,'flock',return_value=None)]
            import contextlib
            with contextlib.ExitStack() as stack:
                for p in patches: stack.enter_context(p)
                if mode=='exception_backstop': stack.enter_context(patch.object(w,'locked_main',side_effect=OSError('synthetic checked fallback error')))
                else:
                    fake=types.SimpleNamespace(activate=lambda **kw:None,start=lambda:None,is_alive=lambda:True,errors=[])
                    stack.enter_context(patch.object(M,'ProcessOwnership',return_value=fake))
                    stack.enter_context(patch.object(M.campaign,'usage_bytes',return_value=0))
                    stack.enter_context(patch.object(w.smi,'query',return_value=dict(target_pids=[])))
                    stack.enter_context(patch.object(w.smi,'admission_problems',return_value=[]))
                    stack.enter_context(patch.object(w,'run_job',return_value=(dict(status='CLEANUP_FAILED',cleanup=dict(errors=['late observer'])), 'CLEANUP_FAILED')))
                    stack.enter_context(patch.object(w,'receipt',side_effect=OSError('synthetic receipt error')))
                try: w.main(); raise AssertionError('unexpected release')
                except Held: pass
            assert len(holds)==1
            result[mode]=dict(result='PASS',holds=holds,scope='mocked main transition; no kernel lease claim')
    result['overall']='PASS'
except BaseException:
    import traceback
    result.update(overall='FAIL; frozen, no in-place retry',trace=traceback.format_exc())
finally:
    (N/'independent-probes.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
