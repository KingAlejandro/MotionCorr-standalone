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
import shutil
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



def procfs_exit_race():
    with tempfile.TemporaryDirectory(prefix='procfs-exit-control-') as folder:
        table=ProcessTable(proc=Path(folder))
        # Exercise the actual read method on either host; a supplied directory
        # selects the Linux implementation without needing a live /proc race.
        for error in (FileNotFoundError(2, 'vanished'), ProcessLookupError(3, 'exited during read')):
            with patch.object(Path,'read_text',side_effect=error):
                require(table.read(424242) is None,'vanished process was treated as unreadable live identity')
        with patch.object(Path,'read_text',side_effect=PermissionError(13,'denied')):
            try:table.read(424242)
            except PermissionError:pass
            else:raise AssertionError('permission failure was treated as disappearance')
    print('PASS actual procfs read handles exit/ESRCH and preserves permission refusal')


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


def refused_cleanup_outcome(helper):
    """A refused signal must produce a bounded failure, not an unbounded wait."""
    with tempfile.TemporaryDirectory(prefix='owned-refused-outcome-') as d:
        tmp=Path(d);receipt=tmp/'worker.json';star=tmp/'movies.star'
        star.write_text('data_movies\n\nloop_\n_rlnMicrographMovieName #1\nMovies/a.tiff\n')
        worker=tmp/'worker'
        worker.write_text('#!'+sys.executable+'\nimport sys;sys.path.insert(0,'+repr(str(ROOT/'tools/multi_gpu'))+')\nimport json,os,pathlib,time\nfrom process_ownership import ProcessTable\npathlib.Path('+repr(str(receipt))+').write_text(json.dumps(ProcessTable().read(os.getpid())))\ntime.sleep(30)\n')
        worker.chmod(0o755)
        wrapper=tmp/'wrapper.py'
        wrapper.write_text('''import importlib.util,os,pathlib,signal,sys,threading,time
sys.path.insert(0,'''+repr(str(ROOT/'tools/multi_gpu'))+''')
sys.path.insert(0,'''+repr(str(helper.parent))+''')
spec=importlib.util.spec_from_file_location('launcher','''+repr(str(helper))+''')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
mod._KILL_REAP_SECONDS=.1
original=mod.ProcessOwnership
class BrokenObserver(original):
    def watch(self,pid):
        super().watch(pid)
        self.errors.append('injected identity observation failure')
mod.ProcessOwnership=BrokenObserver
def interrupt():
    end=time.monotonic()+5
    while not pathlib.Path('''+repr(str(receipt))+''').exists() and time.monotonic()<end:time.sleep(.01)
    os.kill(os.getpid(),signal.SIGTERM)
threading.Thread(target=interrupt,daemon=True).start()
raise SystemExit(mod.main(sys.argv[1:]))
''')
        result=None;timed_out=False
        try:
            try:
                result=subprocess.run([sys.executable,*(['-O'] if not __debug__ else []),str(wrapper),'--star',str(star),'--out',str(tmp/'out'),'--binary',str(worker),'--workers','1','--no-witness'],capture_output=True,text=True,timeout=8)
            except subprocess.TimeoutExpired:timed_out=True
            require(not timed_out,'refused cleanup blocked indefinitely waiting for a still-live worker')
            require(receipt.exists(),'refusal control never launched its worker')
            identity=json.loads(receipt.read_text());current=ProcessTable().read(identity['pid'])
            require(current and same_birth(current['start'],identity['start']) and current['state']!='Z','refused cleanup signalled the unverifiable worker')
            require(result.returncode==128+signal.SIGTERM,'refused interrupted cleanup lost signal outcome: '+str(result.returncode))
            status=json.loads((tmp/'out/status.json').read_text())
            require(status['verdict']=='FAIL' and not status['process_cleanup']['complete'] and status['process_cleanup']['error'],'refused cleanup did not publish explicit FAIL')
            require(status['workers'][0]['returncode'] is None and not status['workers'][0]['exit_observed'] and status['workers'][0]['ended_at'] is None,'unreaped live worker was recorded as exited')
            require(status['final_worker_tail_seconds'] is None,'incomplete worker tail was presented as a measured exit spread')
            print('PASS actual interrupted ownership-refusal returns bounded FAIL with exit unobserved and no unsafe signal')
        finally:
            # Only the fixture author has the independently retained birth;
            # production cleanup correctly refused its own incomplete evidence.
            if receipt.exists():
                identity=json.loads(receipt.read_text());current=ProcessTable().read(identity['pid'])
                if current and same_birth(current['start'],identity['start']) and current['state']!='Z':
                    os.kill(identity['pid'],signal.SIGKILL)


def fast_reparent_outcome(helper):
    """Double fork + setsid between observations: no parent edge is sampled."""
    if sys.platform != 'linux':
        owner = ProcessOwnership()
        refused = False
        try:
            owner.activate(native_required=True)
        except RuntimeError:
            refused = True
        require(refused, 'non-Linux native descendant containment was certified')
        print('UNAVAILABLE Linux double-fork adoption on this host; native execution refusal powered')
        return
    with tempfile.TemporaryDirectory(prefix='owned-fast-reparent-') as d:
        tmp = Path(d); receipt = tmp / 'child.json'; ready = tmp / 'ready'; term = tmp / 'term'
        star = tmp / 'movies.star'
        star.write_text('data_movies\n\nloop_\n_rlnMicrographMovieName #1\nMovies/a.tiff\n')
        worker = tmp / 'worker'
        worker.write_text('#!'+sys.executable+'\n'+"""import json,os,pathlib,signal,sys,time
sys.path.insert(0,"""+repr(str(ROOT/'tools/multi_gpu'))+""")
from process_ownership import ProcessTable
middle=os.fork()
if middle==0:
    child=os.fork()
    if child:os._exit(0)
    os.setsid()
    signal.signal(signal.SIGTERM,lambda s,f:pathlib.Path("""+repr(str(term))+""").write_text('TERM_IGNORED'))
    pathlib.Path("""+repr(str(receipt))+""").write_text(json.dumps(ProcessTable().read(os.getpid())))
    pathlib.Path("""+repr(str(ready))+""").write_text('ready')
    time.sleep(30)
    os._exit(0)
os.waitpid(middle,0)
end=time.monotonic()+5
while not pathlib.Path("""+repr(str(ready))+""").exists() and time.monotonic()<end:time.sleep(.001)
if not pathlib.Path("""+repr(str(ready))+""").exists():raise RuntimeError('grandchild never ready')
os._exit(0)
""")
        worker.chmod(0o755)
        wrapper = tmp / 'wrapper.py'
        wrapper.write_text("""import importlib.util,sys
sys.path.insert(0,"""+repr(str(helper.parent))+""")
spec=importlib.util.spec_from_file_location('launcher',"""+repr(str(helper))+""")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
original=mod.ProcessOwnership
class SlowObserver(original):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.interval=30 # deliberately no observation of either intermediate edge
mod.ProcessOwnership=SlowObserver
mod._TERMINATE_GRACE_SECONDS=.1
mod._KILL_REAP_SECONDS=2
raise SystemExit(mod.main(sys.argv[1:]))
""")
        identity=None
        try:
            cp=subprocess.run([sys.executable,*(['-O'] if not __debug__ else []),str(wrapper),'--star',str(star),'--out',str(tmp/'out'),'--binary',str(worker),'--workers','1','--no-witness'],capture_output=True,text=True,timeout=12)
            require(receipt.exists(),'fast child never wrote identity: '+cp.stdout+cp.stderr)
            identity=json.loads(receipt.read_text());current=ProcessTable().read(identity['pid'])
            require(not(current and same_birth(current['start'],identity['start']) and current['state']!='Z'),'fast double-fork setsid child survived launcher cleanup')
            require(term.exists(),'fast adopted child received no checked TERM before KILL')
            require(cp.returncode==3,'unexpected adopted child did not retain FAIL: '+cp.stdout+cp.stderr)
            status=json.loads((tmp/'out/status.json').read_text());cleanup=status['process_cleanup']
            require(status['workers'][0]['returncode']==0,'original return replaced')
            require(cleanup['ownership_mode']=='linux-child-subreaper' and cleanup['complete'] and cleanup['unexpected_descendants'],'adoption/drain not certified')
            require(any(r['pid']==identity['pid'] and same_birth(r['start'],identity['start']) for r in cleanup['observed_live_before_cleanup']),'actual orphan birth not retained')
            print('PASS actual unsampled double-fork setsid TERM-ignoring child adopted/drained; original0 retained as FAIL')
        finally:
            if identity is None and receipt.exists():identity=json.loads(receipt.read_text())
            if identity:
                current=ProcessTable().read(identity['pid'])
                if current and same_birth(current['start'],identity['start']) and current['state']!='Z':os.kill(identity['pid'],signal.SIGKILL)


def fast_aggregate_outcome(helper):
    """An unsampled orphan from the aggregate owner cannot certify dataset ready."""
    if sys.platform != 'linux':
        print('UNAVAILABLE Linux aggregate orphan-adoption control on this host')
        return
    with tempfile.TemporaryDirectory(prefix='owned-fast-aggregate-') as d:
        tmp=Path(d);tools=tmp/'tools';shutil.copytree(helper.parent,tools)
        receipt=tmp/'child.json';term=tmp/'term';ready=tmp/'ready'
        star=tmp/'movies.star';star.write_text('data_movies\n\nloop_\n_rlnMicrographMovieName #1\nMovies/a.tiff\n')
        shutil.copyfile(tools/'merge_workers.py',tools/'merge_real.py')
        merge_script="""import json,os,pathlib,signal,subprocess,sys,time
rc=subprocess.call([sys.executable,"""+repr(str(tools/'merge_real.py'))+""",*sys.argv[1:]])
if rc:raise SystemExit(rc)
mid=os.fork()
if mid==0:
    if os.fork():os._exit(0)
    os.setsid()
    sys.path.insert(0,"""+repr(str(ROOT/'tools/multi_gpu'))+""")
    from process_ownership import ProcessTable
    signal.signal(signal.SIGTERM,lambda s,f:pathlib.Path("""+repr(str(term))+""").write_text('TERM_IGNORED'))
    pathlib.Path("""+repr(str(receipt))+""").write_text(json.dumps(ProcessTable().read(os.getpid())))
    pathlib.Path("""+repr(str(ready))+""").write_text('ready')
    time.sleep(30);os._exit(0)
os.waitpid(mid,0)
end=time.monotonic()+5
while not pathlib.Path("""+repr(str(ready))+""").exists() and time.monotonic()<end:time.sleep(.001)
if not pathlib.Path("""+repr(str(ready))+""").exists():raise RuntimeError('aggregate grandchild never ready')
os._exit(0)
"""
        (tools/'merge_workers.py').write_text(merge_script)
        wrapper=tmp/'invoke.py';wrapper.write_text("""import sys
sys.path.insert(0,"""+repr(str(tools))+""")
import run_dataset as dataset
original=dataset.ProcessOwnership
class SlowObserver(original):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.interval=30
dataset.ProcessOwnership=SlowObserver
dataset.run_multi_gpu._KILL_REAP_SECONDS=2
def cleanup(procs,ownership):
    dataset.run_multi_gpu._terminate_process_groups(procs,grace_seconds=.1,ownership=ownership)
    return 'checked cleanup control'
dataset.cleanup=cleanup
raise SystemExit(dataset.main(sys.argv[1:]))
""")
        identity=None
        try:
            cp=subprocess.run([sys.executable,*(['-O'] if not __debug__ else []),str(wrapper),'--binary',str(ROOT/'tests/fake_worker.py'),'--star',str(star),'--out',str(tmp/'out'),'--launcher-args=--workers 1 --no-witness','--required-products=.mrc,.star'],capture_output=True,text=True,timeout=15)
            require(receipt.exists(),'aggregate fixture never produced products/orphan: '+cp.stdout+cp.stderr+((tmp/'out/aggregate.log').read_text() if (tmp/'out/aggregate.log').exists() else ''))
            identity=json.loads(receipt.read_text());current=ProcessTable().read(identity['pid'])
            require(not(current and same_birth(current['start'],identity['start']) and current['state']!='Z'),'fast aggregate orphan survived coordinator')
            status=json.loads((tmp/'out/dataset_status.json').read_text())
            require(cp.returncode==3 and not status['dataset_ready'] and status['verdict']=='FAIL','aggregate orphan certified dataset ready')
            require(status['workers_complete'] and status['ownership_mode']=='linux-child-subreaper','healthy worker phase or adoption proof lost')
            require(term.exists(),'aggregate orphan received no checked TERM')
            print('PASS actual healthy workers/aggregate products plus unsampled setsid orphan drain before dataset FAIL')
        finally:
            if identity is None and receipt.exists():identity=json.loads(receipt.read_text())
            if identity:
                current=ProcessTable().read(identity['pid'])
                if current and same_birth(current['start'],identity['start']) and current['state']!='Z':os.kill(identity['pid'],signal.SIGKILL)


def subreaper_boundaries():
    if sys.platform != 'linux':
        return
    lib = __import__('ctypes').CDLL(None,use_errno=True)
    def state():
        value=__import__('ctypes').c_int()
        require(lib.prctl(37,__import__('ctypes').byref(value),0,0,0)==0,'subreaper state unreadable')
        return value.value
    before=state()
    owner=ProcessOwnership();original_read=owner.table.read
    with patch.object(owner.table,'read',lambda pid: None if pid==os.getpid() else original_read(pid)):
        refused=False
        try:owner.activate(native_required=True)
        except RuntimeError:refused=True
    require(refused and not owner.adoption and state()==before,'missing launcher birth accepted activation or changed state')
    print('PASS actual activation refuses missing launcher PID/birth before prctl')
    owner=ProcessOwnership();owner.activate(native_required=True)
    require(state()==1 and owner.mode=='linux-child-subreaper','subreaper enable/readback failed')
    # Unreadable birth of an adopted/direct child must refuse, not drop it.
    proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
    identity=owner.table.read(proc.pid)
    try:
        original=owner.table.read
        def unreadable(pid):
            if pid==proc.pid:raise PermissionError('injected adopted child birth unreadable')
            return original(pid)
        with patch.object(owner.table,'read',unreadable):
            refused=False
            try:owner.refresh()
            except PermissionError:refused=True
        require(refused,'adopted child identity failure silently omitted')
    finally:
        current=owner.table.read(proc.pid)
        if current and current['start']==identity['start']:os.kill(proc.pid,signal.SIGKILL)
        proc.wait(timeout=5)
        owner.restore()
    require(state()==before,'previous subreaper state not restored')
    proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
    identity=ProcessTable().read(proc.pid)
    try:
        owner=ProcessOwnership();refused=False
        try:owner.activate(native_required=True)
        except RuntimeError as exc:refused='pre-existing' in str(exc)
        current=ProcessTable().read(proc.pid)
        require(refused and current and current['start']==identity['start'] and current['state']!='Z','pre-existing child was adopted or disturbed')
        require(state()==before,'pre-existing-child refusal changed subreaper state')
    finally:
        proc.kill();proc.wait(timeout=5)
    print('PASS actual subreaper readback/restoration, missing-birth refusal and pre-existing live-child preservation')
    class Prctl:
        def __init__(self, failure):self.failure=failure;self.value=before;self.gets=0
        def __call__(self, op, arg, *unused):
            if op == 37:
                self.gets += 1
                if self.failure == 'initial-read':return -1
                arg._obj.value = 0 if self.failure == 'readback' and self.gets == 2 else self.value
                return 0
            if self.failure == 'set' and arg == 1:return -1
            self.value=arg
            return 0
    for failure in ('initial-read','set','readback'):
        fake=type('Lib',(),{})();fake.prctl=Prctl(failure);owner=ProcessOwnership();refused=False
        with patch('process_ownership.ctypes.CDLL',return_value=fake):
            try:owner.activate(native_required=True)
            except (OSError,RuntimeError):refused=True
            require(refused,'subreaper '+failure+' accepted worker launch')
            if failure=='readback':require(owner.adoption,'failed readback lost restoration responsibility')
            if owner.adoption:owner.restore()
            require(fake.prctl.value==before,'failed readback did not restore previous mocked state')
        require(state()==before,'failed activation changed real process state')
    print('PASS initial subreaper read/set/readback failures refuse; real process state unchanged')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--helper',type=Path,default=ROOT/'tools/multi_gpu/run_multi_gpu.py');ap.add_argument('--only',choices=['helper','cli','refusal','fast','aggregate-fast']);a=ap.parse_args()
    if a.only not in ('cli','refusal','fast','aggregate-fast'):
        procfs_exit_race();mod=load(a.helper.resolve());mocked(mod);live(mod)
    if a.only not in ('helper','refusal','fast','aggregate-fast'):cli_outcomes(a.helper.resolve())
    if a.only not in ('helper','fast','aggregate-fast'):refused_cleanup_outcome(a.helper.resolve())
    if a.only in (None,'fast'):
        fast_reparent_outcome(a.helper.resolve());subreaper_boundaries()
    if a.only in (None,'fast','aggregate-fast'):
        fast_aggregate_outcome(a.helper.resolve())
    return 0

if __name__=='__main__':raise SystemExit(main())
