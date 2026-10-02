#!/usr/bin/env python3
"""Exercise the actual cleanup helper with PID/birth refusal and owned children.

Mocked recycled groups never signal a real process. The live case creates only
its own new session and observes the child before the root exits.
"""
from __future__ import annotations
import argparse
import importlib.util
import inspect
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
from process_ownership import ProcessOwnership


def require(ok,message):
    if not ok: raise AssertionError(message)


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


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--helper',type=Path,default=ROOT/'tools/multi_gpu/run_multi_gpu.py');a=ap.parse_args()
    mod=load(a.helper.resolve());mocked(mod);live(mod);return 0

if __name__=='__main__':raise SystemExit(main())
