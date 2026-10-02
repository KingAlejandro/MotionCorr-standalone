#!/usr/bin/env python3
"""Powered fake-worker dataset completion and failure-publication controls."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_multi_gpu_scheduling import build_star, DEFAULT_ROWS


def require(ok,message):
    if not ok:raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix='dataset-endpoint-') as td:
        tmp=Path(td);star=tmp/'movies.star';build_star(star,DEFAULT_ROWS)
        def run(name,extra=[]):
            out=tmp/name
            cp=subprocess.run([sys.executable,str(ROOT/'tools/multi_gpu/run_dataset.py'),
                               '--binary',str(ROOT/'tests/fake_worker.py'),'--star',str(star),
                               '--out',str(out),'--required-products','.mrc,.star',
                               '--launcher-args=--workers 2 --no-witness','--',*extra],
                               capture_output=True,text=True)
            return cp,json.loads((out/'dataset_status.json').read_text()),out
        cp,status,out=run('healthy')
        require(cp.returncode==0,cp.stdout+cp.stderr+'\n'+(out/'aggregate.log').read_text())
        require(status['workers_complete'] and status['dataset_ready'] and status['verdict']=='PASS',str(status))
        require(status['dataset_wall_s']>=status['worker_phase_wall_s']+status['aggregate_phase_wall_s'],
                'dataset timer excludes worker/aggregation')
        require((out/'merged/logfile.pdf').is_file(),'missing requested final report')
        require(status['tree_rss']['peak_simultaneous_sum_rss_kib'] is None
                if status['tree_rss']['status']=='UNAVAILABLE' else True,'unavailable memory became zero')
        print('PASS worker completion followed by canonical dataset readiness/full report endpoint')
        cp,status,out=run('worker-fails',['--fake_fail_rc','7'])
        require(cp.returncode!=0 and not status['workers_complete'] and not status['dataset_ready'],str(status))
        require(not (out/'merged/corrected_micrographs.star').exists(),'failed worker published joint success')
        print('PASS failed worker withholds dataset completion')
        cp,status,out=run('report-fails',['--fake_missing_report'])
        require(cp.returncode!=0 and status['workers_complete'] and not status['dataset_ready'],str(status))
        require(status['verdict']=='FAIL','worker exit0 laundered report failure into readiness')
        print('PASS report failure after healthy worker exits cannot publish readiness')
        cp,status,out=run('same-byte-rewrite',['--fake_reprocess'])
        require(cp.returncode!=0 and not status['dataset_ready'],'same-content staged rewrite accepted')
        report=json.loads((out/'aggregate.json').read_text())
        require(any('rewrote' in p for p in report['problems']),str(report))
        print('PASS same-byte rewrite rejected by timestamp plus content identity')
        out=tmp/'overridden'
        cp=subprocess.run([sys.executable,str(ROOT/'tools/multi_gpu/run_dataset.py'),
                           '--binary',str(ROOT/'tests/fake_worker.py'),'--star',str(star),'--out',str(out),
                           '--launcher-args=--binary=/bin/true --workers 2 --no-witness'],capture_output=True,text=True)
        require(cp.returncode!=0 and not out.exists(),'equals-form owned binary override launched')
        print('PASS coordinator argument ownership refuses alternate binary before launch')
    return 0

if __name__=='__main__':raise SystemExit(main())
