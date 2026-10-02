#!/usr/bin/env python3
"""Run isolated workers, then one strict complete-dataset aggregate owner.

Worker completion and dataset readiness are different states. Total wall covers
partition/setup, workers, staging and full aggregate report publication. This
records observations, not a speedup claim; timed comparisons require isolation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

import run_multi_gpu
from tree_rss import OwnedTreeSampler
from process_ownership import ProcessOwnership


def cleanup(owned, ownership):
    # Let the nested launcher complete its checked cleanup before escalating
    # observed descendants. Historical numeric groups alone never authorize it.
    run_multi_gpu._terminate_process_groups(owned, grace_seconds=60.0, ownership=ownership)
    return 'Owned PID/birth groups reaped; observed descendants absent or zombies'


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--binary',required=True)
    ap.add_argument('--star',required=True)
    ap.add_argument('--out',required=True)
    ap.add_argument('--launcher-args',default='',help='quoted launcher options, such as devices/cpuset; not worker options')
    ap.add_argument('--required-products',default='.mrc,.star,_shifts.eps')
    ap.add_argument('--sample-interval',type=float,default=0.1)
    ap.add_argument('worker_args',nargs=argparse.REMAINDER)
    a=ap.parse_args(argv)
    out=Path(a.out).resolve()
    if out.exists():
        ap.error('--out already exists; use a fresh dataset run directory')
    worker_args=a.worker_args[1:] if a.worker_args[:1]==['--'] else a.worker_args
    launcher_extra=shlex.split(a.launcher_args)
    if {arg.split('=',1)[0] for arg in launcher_extra} & {'--out','--binary','--star'}:
        ap.error('coordinator owns --out, --binary and --star')
    def option(key):
        value=None
        for i, arg in enumerate(launcher_extra):
            if arg == key and i+1 < len(launcher_extra):value=launcher_extra[i+1]
            elif arg.startswith(key+'='):value=arg.split('=',1)[1]
        return value
    requested=option('--cpus')
    if requested and hasattr(os,'sched_setaffinity'):
        union=set().union(*(run_multi_gpu.parse_cpu_list(mask) for mask in requested.split(';')))
        if not union <= os.sched_getaffinity(0):ap.error('CPU masks exceed actual allocation')
        os.sched_setaffinity(0,union)  # coordinator, sampler and every descendant share the fixed union
    sampler=OwnedTreeSampler(a.sample_interval)
    ownership=ProcessOwnership()
    input_digest=hashlib.sha256(Path(a.star).read_bytes()).hexdigest()
    out.mkdir(parents=True)
    started=time.monotonic()
    status={'workers_complete':False,'dataset_ready':False,'verdict':'FAIL',
            'input_star_sha256':input_digest,
            'binary':str(Path(a.binary).resolve()),
            'binary_sha256':hashlib.sha256(Path(a.binary).read_bytes()).hexdigest(),
            'endpoint':'successful staged products, canonical joint STAR and full report publication',
            'dataset_wall_s':None}
    owned=[]
    old=run_multi_gpu._install_signal_handlers()
    def child(cmd, name):
        with (out/(name+'.log')).open('w') as log, run_multi_gpu._defer_launcher_signals():
            process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            owned.append((len(owned),process,out));sampler.watch(process.pid)
            ownership.watch(process.pid)
        return process.wait()
    sampler.watch(os.getpid())
    sampler.start()
    ownership.start()
    try:
        begin=time.monotonic()
        rc=child([sys.executable,str(Path(__file__).with_name('run_multi_gpu.py')),
                  '--binary',a.binary,'--star',str(Path(a.star).resolve()),'--out',str(out/'workers'),
                  *launcher_extra,'--',*worker_args],'workers')
        status['worker_phase_wall_s']=time.monotonic()-begin
        if rc:
            status['failure']=f'Worker phase exited {rc}'
            return rc
        worker_status=json.loads((out/'workers/status.json').read_text())
        if worker_status.get('verdict')!='PASS':
            status['failure']='Worker status did not pass'
            return 3
        status['workers_complete']=True
        manifest=json.loads(Path(worker_status['manifest']).read_text())
        if manifest.get('input_sha256') != input_digest:
            status['failure']='Input changed between coordinator preflight and worker partition'
            return 3
        if hashlib.sha256(Path(a.binary).read_bytes()).hexdigest() != status['binary_sha256']:
            status['failure']='Binary changed before aggregation'
            return 3
        n=worker_status['n_workers']
        masks=worker_status.get('cpu_masks') or []
        aggregate_mask=set().union(*(run_multi_gpu.parse_cpu_list(mask) for mask in masks if mask))
        aggregate_prefix=['taskset','-c',run_multi_gpu.format_cpu_list(aggregate_mask)] if aggregate_mask else []
        status['aggregate_cpu_mask']=run_multi_gpu.format_cpu_list(aggregate_mask) if aggregate_mask else None
        begin=time.monotonic()
        cmd=aggregate_prefix+[sys.executable,str(Path(__file__).with_name('merge_workers.py')),
             '--manifest',str(out/'workers/shards/shard_manifest.json'),
             '--workers',*[str(out/'workers'/f'w{k}') for k in range(n)],
             '--out',str(out/'merged'),'--status',str(out/'workers/status.json'),
             '--products',a.required_products,'--aggregate-with',a.binary,
             '--input-star',str(Path(a.star).resolve()),
             '--aggregate-args='+shlex.join(worker_args),'--report',str(out/'aggregate.json')]
        rc=child(cmd,'aggregate')
        status['aggregate_phase_wall_s']=time.monotonic()-begin
        if rc:
            status['failure']=f'Aggregate phase exited {rc}'
            return rc
        aggregate=json.loads((out/'aggregate.json').read_text())
        if aggregate.get('verdict')!='PASS' or not aggregate.get('dataset_ready'):
            status['failure']='Complete dataset aggregate did not pass'
            return 3
        ownership.refresh()
        survivors=[p for p in ownership.known_live() if p['pid'] != os.getpid()]
        if survivors:
            status['failure']='Owned descendants remained after dataset publication'
            status['cleanup']=cleanup(owned,ownership)
            return 3
        status['cleanup']='No observed live PID/birth descendants'
        if ownership.errors:
            status['failure']='Process ownership observation failed: '+str(ownership.errors)
            return 3
        status['dataset_ready']=True;status['verdict']='PASS'
        return 0
    except run_multi_gpu.LauncherInterrupted as exc:
        run_multi_gpu._ignore_launcher_signals()
        status['failure']=f'Interrupted by signal {exc.signum}'
        status['cleanup']=cleanup(owned,ownership)
        return 128+exc.signum
    except Exception as exc:
        run_multi_gpu._ignore_launcher_signals()
        status['failure']=f'{type(exc).__name__}: {exc}'
        status['cleanup']=cleanup(owned,ownership)
        return 3
    finally:
        if owned and not status['dataset_ready'] and 'cleanup' not in status:
            try:
                status['cleanup']=cleanup(owned,ownership)
            except Exception as exc:
                status['cleanup_error']=f'{type(exc).__name__}: {exc}'
        status['dataset_wall_s']=time.monotonic()-started
        ownership.stop();ownership.join(timeout=10)
        status['process_ownership_errors']=ownership.errors
        sampler.stop();sampler.join(timeout=10)
        if sampler.is_alive():sampler.errors.append('Sampler did not stop')
        status['tree_rss']=sampler.report()
        (out/'dataset_status.json').write_text(json.dumps(status,indent=2)+'\n')
        run_multi_gpu._restore_signal_handlers(old)

if __name__=='__main__':
    raise SystemExit(main())
