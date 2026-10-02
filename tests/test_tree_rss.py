#!/usr/bin/env python3
"""Powered device-free simultaneous-RSS and ownership controls using a /proc fixture."""
from pathlib import Path
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/multi_gpu'))
from tree_rss import OwnedTreeSampler


def require(ok,message):
    if not ok:raise AssertionError(message)


def put(proc,pid,ppid,start,rss):
    d=proc/str(pid);d.mkdir(exist_ok=True)
    fields=['R',str(ppid),str(pid if ppid==1 else 10),'10']+['0']*18
    fields[19]=str(start)
    (d/'stat').write_text(f'{pid} (process (name)) '+ ' '.join(fields))
    (d/'status').write_text(f'VmRSS:\t{rss} kB\nVmHWM:\t999999 kB\n')
    exe=d/'exe'
    if not exe.is_symlink():exe.symlink_to('/bin/owned-test')
    (d/'smaps_rollup').write_text(f'Pss: {rss//2} kB\n')


def main():
    with tempfile.TemporaryDirectory(prefix='tree-rss-controls-') as td:
        proc=Path(td)
        put(proc,10,1,100,50);put(proc,11,10,101,1000);put(proc,20,1,200,99999)
        s=OwnedTreeSampler(proc=proc);s.watch(10)
        first=s.snapshot();s.samples.append(first)
        require(first['rss_sum_kib']==1050,'owned child omitted or unrelated process admitted')
        require({p['pid'] for p in first['processes']}=={10,11},'ownership not exact')
        require(first['pss_sum_kib']==525,'PSS units/aggregation incorrect')
        put(proc,10,1,100,1000);put(proc,11,10,101,50)
        second=s.snapshot();s.samples.append(second)
        require(second['rss_sum_kib']==1050,'sequential peaks incorrectly summed')
        require(s.report()['peak_simultaneous_sum_rss_kib']==1050,'summed independent HWM instead of instantaneous RSS')
        print('PASS owned parent/child and non-overlapping peaks, unrelated high-RSS process excluded')
        put(proc,11,1,101,2000)
        require(s.snapshot()['rss_sum_kib']==3000,'known child lost across reparenting')
        put(proc,11,1,999,99999)
        require(s.snapshot()['rss_sum_kib']==1000,'reused unrelated PID admitted')
        print('PASS reparented owned child retained, PID reuse excluded')
        (proc/'10/status').write_text('Name: owned\n')
        bad=s.snapshot();s.samples.append(bad);s.errors.extend(bad['errors'])
        require(bad['rss_sum_kib'] is None and bad['errors'],'missing RSS became zero or success')
        require(s.report()['status']=='INCOMPLETE','sampling failure hidden')
        missing=OwnedTreeSampler(proc=proc/'missing');missing.watch(10)
        require(missing.report()['status']=='UNAVAILABLE' and missing.report()['peak_simultaneous_sum_rss_kib'] is None,
                'no /proc became zero or pass')
        print('PASS unavailable/error readings remain explicit')
        broken=OwnedTreeSampler(proc=proc)
        def fail():raise RuntimeError('powered sampler death')
        broken.snapshot=fail;broken.start();broken.join(timeout=2)
        require(not broken.is_alive() and broken.report()['status']=='INCOMPLETE','thread death became PASS')
        print('PASS sampler death is fail-closed evidence')
    return 0

if __name__=='__main__':raise SystemExit(main())
