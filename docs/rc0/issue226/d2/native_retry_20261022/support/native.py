import fcntl, hashlib, json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from health import W, UUID, snapshot, settle

def run(name, cmd, expected=0, diagnostic=None):
    with (W/'logs/commands.jsonl').open('a') as f: f.write(json.dumps({'name':name,'argv':cmd,'cwd':str(W)})+'\n')
    with (W/'logs'/f'{name}.log').open('w') as f: r=subprocess.run(cmd,cwd=W,stdout=f,stderr=subprocess.STDOUT)
    (W/'logs'/f'{name}.exit').write_text(str(r.returncode)+'\n')
    if r.returncode!=expected: raise RuntimeError(f'{name}: exit {r.returncode}, expected {expected}')
    if diagnostic and diagnostic not in (W/'logs'/f'{name}.log').read_text(): raise RuntimeError('missing expected diagnostic')
    return r

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert (W/'logs/build.exit').read_text().strip()=='0'
    gpu=open('/tmp/motioncorr-gpu3-correctness.lock','w'); fcntl.flock(gpu,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # Bench probe both before and immediately after idle/health admission.
    def bench():
        with open('/tmp/motioncorr-bench.lock','w') as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    bench(); snapshot('native-pre',idle=True); bench()
    os.environ['CUDA_VISIBLE_DEVICES']=UUID
    run('native-original', ['ctest','--test-dir','build','-R','^CudaLocalAdmission$','--verbose','--parallel','1'])
    settle('native-original')
    # Isolated negative-control build. Production helper differs by one assignment;
    # preserve both binary identities, restore exact helper before rebuilding.
    lock=open('/tmp/motioncorr-build.lock','w'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    helper=W/'src/src/acc/cuda/cuda_patch_retry_admission.h'; original=helper.read_bytes()
    old_binary=digest(W/'build/cuda_local_admission')
    run('mutant-apply',['patch','-d',str(W/'src'),'-p1','-i',str(W/'support/omit-retry-budget.patch')])
    try:
        mutant_helper=digest(helper)
        run('mutant-compile',['cmake','--build','build','--target','cuda_local_admission','--parallel','2'])
        mutant_binary=digest(W/'build/cuda_local_admission')
        snapshot('mutant-pre',idle=True); bench()
        run('native-omission-mutant',[str(W/'build/cuda_local_admission')],expected=1,
            diagnostic='FAIL: incorrect complete retry admission boundary')
        settle('native-mutant')
    finally:
        helper.write_bytes(original)
    run('restored-compile',['cmake','--build','build','--target','motioncorr','cuda_local_admission','--parallel','2'])
    restored=digest(W/'build/cuda_local_admission')
    (W/'logs/mutant-identities.json').write_text(json.dumps({'original_binary_sha256':old_binary,
        'mutant_binary_sha256':mutant_binary,'restored_binary_sha256':restored,
        'original_helper_sha256':hashlib.sha256(original).hexdigest(),'mutant_helper_sha256':mutant_helper},indent=2)+'\n')
    fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
    snapshot('native-restored-pre',idle=True); bench()
    run('native-restored',[str(W/'build/cuda_local_admission')])
    settle('native-restored')
    # GPU fd remains held until final health has passed.
    fcntl.flock(gpu,fcntl.LOCK_UN); gpu.close()

if __name__=='__main__':
    (W/'logs/native.pid').write_text(str(os.getpid())+'\n')
    (W/'logs/native.started').write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())+'\n')
    rc=0
    try: main()
    except BaseException:
        import traceback; traceback.print_exc(); rc=1
    (W/'logs/native.exit').write_text(str(rc)+'\n')
    (W/'logs/native.finished').write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())+'\n')
    sys.exit(rc)
