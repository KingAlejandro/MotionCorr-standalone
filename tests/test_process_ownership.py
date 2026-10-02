#!/usr/bin/env python3
"""Exercise the actual cleanup helper with PID/birth refusal and owned children.

Mocked recycled groups never signal a real process. The live case creates only
its own new session and observes the child before the root exits.
"""
from __future__ import annotations
import argparse
import importlib.util
import inspect
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/multi_gpu'))
from process_ownership import ProcessOwnership, ProcessTable


def require(ok,message):
    if not ok: raise AssertionError(message)


def same_birth(left,right):
    # libproc returns a tuple, whereas a retained JSON receipt has a list.
    # Linux start ticks remain integers. Compare their serialized identities.
    return json.dumps(left,separators=(',',':'))==json.dumps(right,separators=(',',':'))


def load(path):
    spec=importlib.util.spec_from_file_location('cleanup_under_test',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


class Table:
    def __init__(self):self.rows={}
    def read(self,pid):return dict(self.rows[pid]) if pid in self.rows else None
    def pids(self):return list(self.rows)
    def records(self,known=()):return {p:self.read(p) for p in self.rows}
    def group_live(self,group):return any(r['pgid']==group and r['state']!='Z' for r in self.rows.values())


def row(pid,start,group,parent=1):
    return {'pid':pid,'start':start,'pgid':group,'ppid':parent,'state':'R'}


class Exited:
    def __init__(self,pid):self.pid=pid
    def poll(self):return 0
    def wait(self,timeout=None):return 0


def invoke(mod,roots,owner,grace=0):
    kwargs={'grace_seconds':grace}
    if 'ownership' in inspect.signature(mod._terminate_process_groups).parameters:
        kwargs['ownership']=owner
    return mod._terminate_process_groups(roots,**kwargs)


def mocked(mod):
    group=424242;table=Table();table.rows[group]=row(group,10,group)
    owner=ProcessOwnership(table=table);owner.watch(group)
    table.rows[group]=row(group,11,group) # same number, different process birth
    signals=[]
    with patch.object(mod,'_KILL_REAP_SECONDS',0),patch.object(mod,'_process_group_exists',table.group_live),patch.object(mod.os,'killpg',lambda g,s:signals.append((g,s))):
        error=None
        try:invoke(mod,[(0,Exited(group),Path('.'))],owner)
        except RuntimeError as exc:error=str(exc)
    require(not signals,'recycled historical PGID was signalled: '+str(signals))
    require(error and 'unverified' in error,'unverified ownership must fail cleanup explicitly')
    print('PASS recycled original PID/birth refused without any signal')

    table=Table();table.rows[group]=row(group,10,group);table.rows[group+1]=row(group+1,20,group,group)
    owner=ProcessOwnership(table=table);owner.watch(group);owner.refresh()
    del table.rows[group];table.rows[group+1]['ppid']=1
    table.rows[group+2]=row(group+2,30,group+2)
    signals=[]
    def terminate(g,s):
        signals.append((g,s))
        if s==signal.SIGKILL:
            for pid in list(table.rows):
                if table.rows[pid]['pgid']==g:del table.rows[pid]
    with patch.object(mod,'_KILL_REAP_SECONDS',0),patch.object(mod,'_process_group_exists',table.group_live),patch.object(mod.os,'killpg',terminate):
        invoke(mod,[(0,Exited(group),Path('.'))],owner)
    require(signals==[(group,signal.SIGTERM),(group,signal.SIGKILL)],'owned reparented TERM-ignoring group was not escalated: '+str(signals))
    require(group+2 in table.rows,'unrelated process was touched')
    print('PASS observed reparented child escalates; unrelated group untouched')

    # A second signal must recheck birth, even if the initial TERM was owned.
    table=Table();table.rows[group]=row(group,10,group);owner=ProcessOwnership(table=table);owner.watch(group);signals=[]
    def recycle(g,s):
        signals.append((g,s));table.rows[group]=row(group,99,group)
    with patch.object(mod,'_KILL_REAP_SECONDS',0),patch.object(mod,'_process_group_exists',table.group_live),patch.object(mod.os,'killpg',recycle):
        error=None
        try:invoke(mod,[(0,Exited(group),Path('.'))],owner)
        except RuntimeError as exc:error=str(exc)
    require(signals==[(group,signal.SIGTERM)],'KILL used stale ownership after TERM: '+str(signals))
    require(error and 'unverified' in error,'birth change between signals did not fail closed')
    print('PASS every escalation rechecks original PID/birth')

    table=Table();table.rows[group]=row(group,10,group)
    owner=ProcessOwnership(table=table);owner.watch(group);owner.errors.append('injected ownership observation failure')
    signals=[]
    with patch.object(mod,'_KILL_REAP_SECONDS',0),patch.object(mod,'_process_group_exists',table.group_live),patch.object(mod.os,'killpg',lambda g,s:signals.append((g,s))):
        error=None
        try:invoke(mod,[(0,Exited(group),Path('.'))],owner)
        except RuntimeError as exc:error=str(exc)
    require(not signals and error and 'unverified' in error,'observation failure must refuse every signal despite retained original PID')
    print('PASS observer error fails closed before any signal')


def live(mod):
    with tempfile.TemporaryDirectory(prefix='owned-cleanup-') as d:
        tmp=Path(d);pidfile=tmp/'pid';release=tmp/'release';ready=tmp/'ready'
        child="import signal,time,pathlib;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path("+repr(str(ready))+").write_text('ready');time.sleep(30)"
        parent="import subprocess,sys,pathlib,time;p=subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);pathlib.Path("+repr(str(pidfile))+").write_text(str(p.pid));\nwhile not pathlib.Path("+repr(str(release))+").exists():time.sleep(.01)\n"
        proc=subprocess.Popen([sys.executable,'-c',parent],start_new_session=True)
        owner=ProcessOwnership();owner.watch(proc.pid)
        try:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                owner.refresh()
                if ready.exists() and pidfile.exists() and int(pidfile.read_text()) in owner.identities:break
                time.sleep(.01)
            require(ready.exists() and pidfile.exists(),'owned child did not become ready')
            childpid=int(pidfile.read_text());require(childpid in owner.identities,'child birth was not observed before reparenting')
            release.write_text('exit');require(proc.wait(timeout=5)==0,'parent failed')
            require(any(r['pid']==childpid for r in owner.known_live()),'child did not survive exited parent')
            with patch.object(mod,'_KILL_REAP_SECONDS',2):
                invoke(mod,[(0,proc,tmp)],owner,grace=.1)
            require(not owner.known_live(),'owned child remains live after escalation')
            print('PASS actual new-session TERM-ignoring child reaped after original parent exits')
        finally:
            # Fixture cleanup is bound to the identities created/observed here.
            for rec in owner.known_live():
                try:os.kill(rec['pid'],signal.SIGKILL)
                except ProcessLookupError:pass
            proc.wait(timeout=5)


def cli_outcomes(helper):
    """Actual launcher lifecycle, not just direct calls of its cleanup helper."""
    with tempfile.TemporaryDirectory(prefix='owned-worker-outcome-') as d:
        tmp=Path(d);star=tmp/'movies.star'
        star.write_text('data_movies\n\nloop_\n_rlnMicrographMovieName #1\nMovies/a.tiff\n')
        for exit_code,new_session in ((7,False),(0,True)):
            case=tmp/('exit'+str(exit_code));case.mkdir();receipt=case/'child.json';ready=case/'ready';term=case/'term'
            child_code='import json,os,pathlib,signal,time\nfrom process_ownership import ProcessTable\nsignal.signal(signal.SIGTERM,lambda s,f:pathlib.Path('+repr(str(term))+').write_text("TERM_RECEIVED_IGNORED"))\nidentity=ProcessTable().read(os.getpid())\npathlib.Path('+repr(str(receipt))+').write_text(json.dumps(identity))\npathlib.Path('+repr(str(ready))+').write_text("ready")\ntime.sleep(30)\n'
            worker=case/'worker'
            worker.write_text(f'''#!{sys.executable}
import pathlib,subprocess,sys,time
tools={str(ROOT/'tools/multi_gpu')!r}
child={child_code!r}
prefix='import sys;sys.path.insert(0,'+repr(tools)+');'
p=subprocess.Popen([sys.executable,'-c',prefix+child],start_new_session={new_session!r})
end=time.monotonic()+5
while not pathlib.Path({str(ready)!r}).exists() and time.monotonic()<end:time.sleep(.01)
if not pathlib.Path({str(ready)!r}).exists():raise RuntimeError('child startup failed')
time.sleep(.5)
print('ORIGINAL_WORKER_RETURN_{exit_code}',file=sys.stderr,flush=True)
sys.exit({exit_code})
''')
            worker.chmod(0o755)
            command=[sys.executable,*(['-O'] if not __debug__ else []),str(helper),'--star',str(star),'--out',str(case/'out'),'--binary',str(worker),'--workers','1','--no-witness']
            identity=None
            try:
                result=subprocess.run(command,capture_output=True,text=True,timeout=20)
                require(receipt.exists(),'actual worker child did not write birth receipt: '+result.stdout+result.stderr+((case/'out/w0/run.log').read_text() if (case/'out/w0/run.log').exists() else ''))
                identity=json.loads(receipt.read_text());current=ProcessTable().read(identity['pid'])
                require(not(current and same_birth(current['start'],identity['start']) and current['state']!='Z'),'actual normal-return '+str(exit_code)+' left owned reparented child live')
                require(term.exists(),'actual normal-return '+str(exit_code)+' did not send checked TERM before escalation')
                require(result.returncode==3,'normal worker outcome with live child incorrectly passed or signal-aborted: '+str(result.returncode))
                status=json.loads((case/'out/status.json').read_text())
                require(status['verdict']=='FAIL' and not status['workers_complete'],'unexpected descendant became worker success')
                require(status['workers'][0]['returncode']==exit_code,'checked cleanup replaced original worker return code')
                require('ORIGINAL_WORKER_RETURN_'+str(exit_code) in (case/'out/w0/run.log').read_text(),'original worker diagnostic lost')
                cleanup=status['process_cleanup']
                require(cleanup['complete'] and cleanup['error'] is None and cleanup['unexpected_descendants'],'normal return cleanup not explicitly complete')
                require(any(r['pid']==identity['pid'] and r['start']==identity['start'] and r['ppid']!=status['workers'][0]['pid'] for r in cleanup['observed_live_before_cleanup']),'cleanup did not prove same-birth reparented descendant')
                print('PASS actual worker exit'+str(exit_code)+' reparented TERM-ignoring descendant drained before FAIL; original return retained')
            finally:
                if identity is None and receipt.exists():identity=json.loads(receipt.read_text())
                if identity:
                    current=ProcessTable().read(identity['pid'])
                    if current and same_birth(current['start'],identity['start']) and current['state']!='Z':
                        os.kill(identity['pid'],signal.SIGKILL)

        # A quiescent healthy worker still reaches PASS; no missing-child fixture
        # or blanket refusal can satisfy the failure controls above.
        worker=tmp/'healthy-worker';worker.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(.1)\n');worker.chmod(0o755)
        result=subprocess.run([sys.executable,*(['-O'] if not __debug__ else []),str(helper),'--star',str(star),'--out',str(tmp/'healthy-out'),'--binary',str(worker),'--workers','1','--no-witness'],capture_output=True,text=True,timeout=10)
        require(result.returncode==0,'quiescent healthy worker refused: '+result.stderr)
        status=json.loads((tmp/'healthy-out/status.json').read_text())
        require(status['verdict']=='PASS' and status['process_cleanup']['complete'] and status['process_cleanup']['observed_live_before_cleanup']==[],'healthy quiescent outcome not checked and complete')
        print('PASS actual healthy no-descendant worker retains PASS')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--helper',type=Path,default=ROOT/'tools/multi_gpu/run_multi_gpu.py');ap.add_argument('--only',choices=['helper','cli']);a=ap.parse_args()
    if a.only!='cli':
        mod=load(a.helper.resolve());mocked(mod);live(mod)
    if a.only!='helper':cli_outcomes(a.helper.resolve())
    return 0

if __name__=='__main__':raise SystemExit(main())
