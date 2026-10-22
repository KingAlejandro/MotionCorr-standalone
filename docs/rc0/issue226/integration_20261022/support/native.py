"""One combined-source native qualification, no retry or source mutation."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from health import W,UUID,snapshot,settle

def bench():
    with open('/tmp/motioncorr-bench.lock','w') as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)

def run(name,cmd):
    bench(); snapshot(name+'-pre',idle=True); bench()
    receipt=dict(name=name,argv=cmd,cwd=str(W),affinity=sorted(os.sched_getaffinity(0)),utc=time.strftime('%FT%TZ',time.gmtime()))
    with (W/'logs'/f'{name}.log').open('w') as log:
        p=subprocess.Popen(cmd,cwd=W,stdout=log,stderr=subprocess.STDOUT)
        receipt['pid']=p.pid
        (W/'logs'/f'{name}-driver.json').write_text(json.dumps(receipt,indent=2)+'\n')
        rc=p.wait()
    receipt['exit']=rc
    (W/'logs'/f'{name}-driver.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (W/'logs'/f'{name}.exit').write_text(str(rc)+'\n')
    settle(name)
    if rc: raise RuntimeError(f'{name} exit {rc}')

def main():
    assert (W/'logs/complete-build.exit').read_text().strip()=='0'
    with open('/tmp/motioncorr-gpu3-correctness.lock','w') as gpu:
        fcntl.flock(gpu,fcntl.LOCK_EX|fcntl.LOCK_NB)
        os.environ['CUDA_VISIBLE_DEVICES']=UUID
        os.environ['MC_D3_SAMPLE_GUARD']=str(W/'support/d3_guard.py')
        bench(); snapshot('native-initial-pre',idle=True); bench()
        run('local-admission',['ctest','--test-dir','build','-R','^CudaLocalAdmission$','--verbose','--parallel','1'])
        run('early-oom',[sys.executable,'src/tests/run_early_streaming_oom.py','--binary','build/motioncorr_faultinject','--root',str(W/'early')])
        run('plan-matrix',[sys.executable,'src/tests/run_streaming_plan_classification_cleanup.py','--binary','build/motioncorr_streaming_plan_fault','--root',str(W/'matrix')])
        settle('native-final')

if __name__=='__main__':
    (W/'logs/native.pid').write_text(str(os.getpid())+'\n')
    (W/'logs/native.started').write_text(time.strftime('%FT%TZ',time.gmtime())+'\n')
    rc=0
    try:main()
    except BaseException:
        import traceback; traceback.print_exc();rc=1
    (W/'logs/native.finished').write_text(time.strftime('%FT%TZ',time.gmtime())+'\n')
    (W/'logs/native.exit').write_text(str(rc)+'\n')
    sys.exit(rc)
