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
        # A top-level movie run.tif writes run.log, which was also the launcher's
        # console log for each worker: the two streams shared one file. The
        # movie's own log must reach merged/ intact and the console log must be
        # staged separately under _workers/.
        log_star=tmp/'run_log.star';build_star(log_star,[('run.tif',1,0.0),('Movies/x.tiff',1,1.4)])
        out=tmp/'run-log-collision'
        cp=subprocess.run([sys.executable,str(ROOT/'tools/multi_gpu/run_dataset.py'),
                           '--binary',str(ROOT/'tests/fake_worker.py'),'--star',str(log_star),
                           '--out',str(out),'--required-products','.mrc,.star,.log',
                           '--launcher-args=--workers 2 --no-witness','--','--fake_sleep_per_movie','0.01'],
                           capture_output=True,text=True)
        require(cp.returncode==0,cp.stdout+cp.stderr)
        require((out/'merged/run.log').read_text()=='FAKELOG run.tif\nFull movie wall time: 0.010 s\n',
                'movie run.log was mixed with or replaced by the launcher console: '
                +repr((out/'merged/run.log').read_text()))
        consoles=[(out/'merged/_workers'/f'w{k}'/'launcher.console.log').read_text() for k in range(2)]
        require(all('fake_worker processed 1 movie(s)' in c for c in consoles),str(consoles))
        workers=json.loads((out/'workers/status.json').read_text())
        for w in workers['workers']:
            require(w['log'].endswith('/launcher.console.log'),w['log'])
            require(w['phases']['binary_movie_walls_missing']==[] and
                    w['phases']['binary_movie_wall_sum']==0.01,str(w['phases']))
        print('PASS top-level run.tif keeps its run.log; launcher console log is a separate staged file')
        # A worker whose per-movie logs are absent has no binary movie time; the
        # sum must say so rather than read as 0 s or as a partial total.
        out=tmp/'missing-movie-logs'
        cp=subprocess.run([sys.executable,str(ROOT/'tools/multi_gpu/run_dataset.py'),
                           '--binary',str(ROOT/'tests/fake_worker.py'),'--star',str(star),
                           '--out',str(out),'--required-products','.mrc,.star',
                           '--launcher-args=--workers 2 --no-witness','--','--fake_no_movie_log'],
                           capture_output=True,text=True)
        require(cp.returncode==0,cp.stdout+cp.stderr)
        workers=json.loads((out/'workers/status.json').read_text())
        manifest=json.loads((out/'workers/shards/shard_manifest.json').read_text())
        for w in workers['workers']:
            require(w['phases']['binary_movie_wall_sum'] is None,str(w['phases']))
            require(w['phases']['binary_movie_walls_missing']==manifest['shards'][w['index']]['movies'],
                    str(w['phases']))
        print('PASS missing per-movie wall times are reported as missing, not as zero')
        out=tmp/'overridden'
        cp=subprocess.run([sys.executable,str(ROOT/'tools/multi_gpu/run_dataset.py'),
                           '--binary',str(ROOT/'tests/fake_worker.py'),'--star',str(star),'--out',str(out),
                           '--launcher-args=--binary=/bin/true --workers 2 --no-witness'],capture_output=True,text=True)
        require(cp.returncode!=0 and not out.exists(),'equals-form owned binary override launched')
        print('PASS coordinator argument ownership refuses alternate binary before launch')
    return 0

if __name__=='__main__':raise SystemExit(main())
