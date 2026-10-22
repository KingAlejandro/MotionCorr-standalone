#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import datetime, fcntl, hashlib, json, os, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1]); logs=root/'build-logs'; logs.mkdir(exist_ok=False)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(label,argv):
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (logs/(label+'.log')).open('w') as f:
        p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
        (logs/(label+'.pid')).write_text(str(p.pid)+'\n');rc=p.wait()
    (logs/(label+'.json')).write_text(json.dumps(dict(argv=argv,start=start,exit=rc,pid=p.pid,affinity=sorted(os.sched_getaffinity(0))),indent=2)+'\n')
    if rc: raise RuntimeError(label)
def main():
    assert os.sched_getaffinity(0)=={10,11,12,13}
    os.environ.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with open('/tmp/motioncorr-build.lock','a') as f:
        try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            run('busy-owners',['lslocks','--output','PID,COMMAND,PATH']);raise RuntimeError('UNRUN build lock busy; no retry')
        (logs/'lock.json').write_text(json.dumps(dict(pid=os.getpid(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),path=f.name,mode='exclusive nonblocking'))+'\n')
        run('toolchain',['bash','-c','hostname; cmake --version; g++ --version; /usr/local/cuda-12.8/bin/nvcc --version; /home/alex/.mc-venv/bin/python3 -c "import numpy; print(numpy.__version__)"; df -h /mnt/clathrin'])
        for kind in ['cpu','cuda']:
            b=root/('build-'+kind)
            opts=['-DCUDA=OFF'] if kind=='cpu' else ['-DCUDA=ON','-DUSE_NVCOMP=OFF','-DCMAKE_CUDA_ARCHITECTURES=80','-DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc','-DCUDAToolkit_ROOT=/usr/local/cuda-12.8']
            run('configure-'+kind,['cmake','-S',str(root/'src'),'-B',str(b),'-DCMAKE_BUILD_TYPE=Release','-DBUILD_TESTING=OFF','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3']+opts)
            run('compile-'+kind,['cmake','--build',str(b),'--target','motioncorr','--parallel','2'])
            run('ldd-'+kind,['ldd',str(b/'motioncorr')])
        (root/'binaries.json').write_text(json.dumps({k:sha(root/('build-'+k)/'motioncorr') for k in ['cpu','cuda']},indent=2)+'\n')
rc=0
try:main()
except Exception as e:print(repr(e),flush=True);rc=1
(root/'build.exit').write_text(str(rc)+'\n');sys.exit(rc)
