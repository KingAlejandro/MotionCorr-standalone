#!/usr/bin/env python3
"""Linux CPU8-9 harmless integration controls. Retains every attempt; no native.
usage: test_startup.py PACKET_DIR FROZEN_CPU1C_DIR NEW_EXCLUSIVE_CONTROL_ROOT
"""
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

packet, old, root = map(lambda x: Path(x).resolve(), sys.argv[1:])
root.mkdir()  # exclusive; no lost attempts
assert next(l.split(':')[1].strip() for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('Cpus_allowed_list')) == '8-9'
results = []

def setup(name, body=None, stale=None):
    sc = root / name
    (sc / 'logs').mkdir(parents=True)
    for marker in ('cpu1c-launch', 'cpu1c-launch2'):
        (sc / 'logs' / marker).mkdir()
    (sc / 'logs/chain-cpu1d.go').write_text('CONTROL ONLY\n')
    (sc / 'lease').touch()  # existing file: reproduces noclobber precondition
    if stale:
        p = sc / 'logs' / stale
        if stale.endswith('.reserved'):
            p.mkdir()
        elif stale.endswith('.dangling'):
            p.symlink_to(sc / 'absent')
        else:
            p.write_text('stale must block\n')
    if body is None:
        body = f'''export C1_SCR={sc} C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f
bash {packet}/tools/c1_stage.sh cpu1d-prereq /home/alex/.mc-venv/bin/python3 -B {packet}/namespace_control.py {packet}/cpu1d_prereq.py {sc} {sc}/namespace.json
'''
    (sc / 'mock-chain.sh').write_text('#!/bin/bash\n' + body)
    return sc

def launch(sc, expected, extra_env=None):
    env = dict(os.environ, CPU1D_SC=str(sc), CPU1D_LOCK=str(sc/'lease'), CPU1D_CHAIN=str(sc/'mock-chain.sh'))
    env.update(extra_env or {})
    out = sc / f'call-{len(list(sc.glob("call-*.json")))}.json'
    cmd = ['bash', str(packet/'cpu1d-launch-wrapper.sh')]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=15)
    out.write_text(json.dumps({'argv': cmd, 'overrides': {k:v for k,v in env.items() if k.startswith('CPU1D_')}, 'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}, indent=2)+'\n')
    assert r.returncode == expected, (sc.name,r.returncode,expected,r.stderr)
    return sc/'logs/launch-cpu1d-attempt1'

def digest_tree(p):
    return {str(x.relative_to(p)):hashlib.sha256(x.read_bytes()).hexdigest() for x in p.rglob('*') if x.is_file()}

# Old *actual* operational wrapper + unchanged actual stage + exact old check.
sc=setup('old-namespace-bug')
(sc/'logs/cpu1c-launch-control').mkdir()
(sc/'mock-chain.sh').write_text(f'export C1_SCR={sc} C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f\nbash {packet}/tools/c1_stage.sh cpu1c-prereq /home/alex/.mc-venv/bin/python3 -B {packet}/namespace_control.py {old}/cpu1c_prereq.py {sc} {sc}/namespace.json\n')
env=dict(os.environ, CPU1C_SC=str(sc),CPU1C_LAUNCH_DIR=str(sc/'logs/cpu1c-launch-control'),CPU1C_LOCK=str(sc/'lease'),CPU1C_CHAIN=str(sc/'mock-chain.sh'),CPU1C_CHAIN_OUT=str(sc/'logs/mock-chain.out'))
r=subprocess.run(['bash',str(old/'cpu1c-launch-wrapper2.sh')],env=env,capture_output=True,text=True,timeout=15)
(sc/'old-wrapper-call.json').write_text(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n')
assert r.returncode==1
assert (sc/'logs/cpu1c-prereq.reserved').is_dir()
assert json.loads((sc/'namespace.json').read_text())['checks']['fresh_stage_names']['ok'] is False
results.append({'control':'old wrapper+stage+exact prerequisite block reproduces namespace FAIL','exit':r.returncode,'status':'PASS'})

sc=setup('new-namespace-pass')
L=launch(sc,0)
ns=json.loads((sc/'namespace.json').read_text())
assert ns['checks']['fresh_stage_names']['ok'] is True
assert {'cpu1d-prereq.reserved','cpu1d-prereq.pid','cpu1d-prereq.started','cpu1d-prereq.log','launch-cpu1d-attempt1','cpu1c-launch','cpu1c-launch2'} <= set(ns['entries'])
for who in ['wrapper','chain']:
    assert (L/f'{who}.cpus').read_text().strip()=='8-9'
    stat=(L/f'{who}.proc-stat').read_text().split(') ',1)[1].split()
    assert int(stat[19])>0  # /proc stat field 22 start ticks
    assert (L/f'{who}.uid').read_text().strip()==str(os.getuid())
    assert (L/f'{who}.argv.nul').read_bytes()
assert (L/'chain.exit').read_text().strip()=='0' and (L/'chain.reaped').exists()
results.append({'control':'new wrapper+actual stage+exact namespace block with own active receipts and old markers','exit':0,'status':'PASS'})
# Reinvoke: marker and all prior artifacts must stay byte-for-byte.
before=digest_tree(L)
launch(sc,4)
assert digest_tree(L)==before
results.append({'control':'atomic one-shot marker refuses reinvocation, receipts unchanged','exit':4,'status':'PASS'})
# Check the append-opened existing file no longer has a lease after chain reap.
with (sc/'lease').open('a') as f:
    fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    fcntl.flock(f,fcntl.LOCK_UN)
results.append({'control':'existing lease file works and lease free after reap','exit':0,'status':'PASS'})
for artifact in ['cpu1d-v2-cpu-c1.reserved','cpu1d-v2-cpu-c1.exit','cpu1d-prereq.unknown','cpu1d-unknown.dangling']:
    sc=setup('stale-'+artifact,stale=artifact)
    launch(sc,1)
    assert json.loads((sc/'namespace.json').read_text())['checks']['fresh_stage_names']['detail']==[artifact]
    results.append({'control':'genuine stale namespace blocks: '+artifact,'exit':1,'status':'PASS'})
# A pre-existing prereq reservation is refused by the unchanged stage wrapper,
# before even its own-receipt exemption can apply.
sc=setup('stale-own-prereq',stale='cpu1d-prereq.reserved')
launch(sc,4)
assert not (sc/'namespace.json').exists()
results.append({'control':'stale own prerequisite reservation blocks in actual stage wrapper','exit':4,'status':'PASS'})
sc=setup('foreign-holder',body='echo CHAIN_RAN > '+str(root/'foreign-chain-ran')+'\n')
with (sc/'lease').open('a') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # Parent test process is a distinct foreign holder to the wrapper, no signal.
    (sc/'holder.proc-stat').write_bytes(Path('/proc/self/stat').read_bytes())
    (sc/'holder.proc-status').write_bytes(Path('/proc/self/status').read_bytes())
    L=launch(sc,7)
    assert (L/'lease.contended').exists() and not (L/'chain.pid').exists()
    assert not (root/'foreign-chain-ran').exists()
assert not (L/'lease.error').exists()
results.append({'control':'foreign held lease stops before chain','exit':7,'status':'PASS'})
sc=setup('child-nonzero',body='exit 5\n')
L=launch(sc,5)
assert (L/'chain.exit').read_text().strip()=='5' and (L/'wrapper.exit').read_text().strip()=='5'
results.append({'control':'child nonzero exit propagates with reap','exit':5,'status':'PASS'})
sc=setup('missing-go',body='exit 0\n')
(sc/'logs/chain-cpu1d.go').unlink()  # only our mock, not shared evidence
L=launch(sc,9)
assert not (L/'chain.pid').exists()
results.append({'control':'missing parent GO stops before chain','exit':9,'status':'PASS'})
sc=setup('open-error',body='exit 0\n')
L=launch(sc,8,{'CPU1D_LOCK':str(sc/'missing-parent/lease')})
assert (L/'lease.error').exists() and not (L/'lease.contended').exists() and not (L/'chain.pid').exists()
results.append({'control':'lease open failure distinct from contention','exit':8,'status':'PASS'})
(root/'RESULTS.json').write_text(json.dumps({'status':'PASS','native_execution':'UNRUN','controls':results},indent=2)+'\n')
print(json.dumps({'status':'PASS','controls':len(results),'root':str(root)}))
