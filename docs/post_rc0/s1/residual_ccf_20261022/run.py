#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Single frozen campaign, at most 16 MotionCorr processes. No retry."""
import datetime,fcntl,hashlib,json,os,pathlib,subprocess,sys,time,re
R=pathlib.Path(sys.argv[1]);P='/home/alex/.mc-venv/bin/python3';U='GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'
L=R/'run-logs';L.mkdir(exist_ok=False);(R/'runs').mkdir(exist_ok=False)
ledger=[];pairs=[];launches=0

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def run(label,argv,env=None,cwd=None,expected=(0,)):
    start=now()
    with (L/(label+'.log')).open('w') as log:
        p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,cwd=cwd,env=env)
        write(L/(label+'.started.json'),dict(pid=p.pid,start=start,argv=argv,cwd=str(cwd or pathlib.Path.cwd()),env={k:v for k,v in (env or {}).items() if k.startswith(("MC_CCF_","CUDA_")) or k in ("PYTHONDONTWRITEBYTECODE","OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","LD_LIBRARY_PATH")},affinity=sorted(os.sched_getaffinity(p.pid))))
        rc=p.wait()
    row=dict(label=label,argv=argv,cwd=str(cwd or pathlib.Path.cwd()),start=start,end=now(),pid=p.pid,exit=rc,expected=list(expected))
    ledger.append(row);write(L/'commands.json',ledger);(L/(label+'.exit')).write_text(str(rc)+'\n')
    assert rc in expected,(label,rc)
    return (L/(label+'.log')).read_text()
def health(label,idle=False):
    mapping=run(label+'-mapping',['nvidia-smi','--query-gpu=index,uuid,name,memory.used,utilization.gpu','--format=csv,noheader,nounits'])
    rows=[r.split(', ') for r in mapping.splitlines() if U in r]
    assert len(rows)==1 and rows[0][0]=='3','GPU UUID/index changed'
    apps=run(label+'-apps',['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader'])
    assert U not in apps,'assigned GPU occupied'
    ecc=run(label+'-ecc',['nvidia-smi','-i',U,'--query-gpu=ecc.errors.corrected.volatile.total,ecc.errors.uncorrected.volatile.total','--format=csv,noheader,nounits'])
    assert ecc.strip()=='0, 0','fatal hardware error/unavailable ECC'
    full=run(label+'-full',['nvidia-smi','-i',U,'-q'])
    assert 'Recovery Action' not in full or all('None' in x for x in full.splitlines() if 'Recovery Action' in x),'hardware recovery action'
    if idle:assert int(rows[0][-1])==0,'GPU not idle'
    return int(rows[0][-1])
def lock(path):
    f=open(path,'a')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        run('busy-owners',['lslocks','--output','PID,COMMAND,PATH']);f.close();raise RuntimeError('UNRUN lock busy: '+path)
    return f

def normalized_mrc(p):
    b=p.read_bytes();return b[:224]+b[1024:]
def normalized_labels(p):
    return re.sub(rb'Relion    [0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}',b'Relion    DD-Mon-YY  HH:MM:SS',p.read_bytes()[224:1024])
def neutral(case,backend):
    a=R/'runs'/f'{backend}-{case}-off';b=R/'runs'/f'{backend}-{case}-on'
    checks={};details={}
    for name in ['global.txt','model.txt']:
        checks['state/'+name]=(a/'state'/name).read_bytes()==(b/'state'/name).read_bytes()
    for name in [case+'.star']:
        checks[name]=(a/'out'/name).read_bytes()==(b/'out'/name).read_bytes()
    ma={str(p.relative_to(a/'out')):p for p in (a/'out').rglob('*.mrc')}
    mb={str(p.relative_to(b/'out')):p for p in (b/'out').rglob('*.mrc')}
    checks['mrc-inventory']=ma.keys()==mb.keys()
    for name in ma.keys()&mb.keys():
        checks[name]=normalized_mrc(ma[name])==normalized_mrc(mb[name])
        checks[name+'-timestamp-only-labels']=normalized_labels(ma[name])==normalized_labels(mb[name])
        details[name]=dict(off_sha256=sha(ma[name]),on_sha256=sha(mb[name]),
            core_and_payload_sha256=hashlib.sha256(normalized_mrc(ma[name])).hexdigest(),
            labels_off=ma[name].read_bytes()[224:1024].decode('ascii','replace'),labels_on=mb[name].read_bytes()[224:1024].decode('ascii','replace'))
    result=dict(case=case,backend=backend,status='PASS' if all(checks.values()) else 'FAIL',checks=checks,mrc=details,
        normalization='existing compare_products.py MRC [0:224]+[1024:] plus exact labels after only Relion timestamp substitution; exact per-movie STAR and pre-write state; no numeric tolerance')
    pairs.append(result);write(R/'neutrality.json',pairs)
    assert result['status']=='PASS','FAIL capture changed result: stop before interpretation'

def main():
    global launches
    assert os.sched_getaffinity(0)=={10,11,12,13}
    assert (R/'build.exit').read_text().strip()=='0'
    binding=json.loads((R/'overlay-binding.json').read_text())
    for name,value in binding['overlay_files'].items():assert sha(R/'src'/name)==value
    bins=json.loads((R/'binaries.json').read_text())
    for k,value in bins.items():assert sha(R/('build-'+k)/'motioncorr')==value
    env={k:v for k,v in os.environ.items() if not k.startswith(('MC_DIAG_','MC_CCF_'))}
    env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',CUDA_VISIBLE_DEVICES=U,CUDA_DEVICE_ORDER='PCI_BUS_ID',LD_LIBRARY_PATH='/usr/local/cuda-12.8/lib64')
    write(L/'environment.json',dict(pid=os.getpid(),utc=now(),hostname=os.uname().nodename,affinity=sorted(os.sched_getaffinity(0)),numeric_threads=1,runtime_threads=1,gpu_uuid=U,driver_sha256=sha(pathlib.Path(__file__))))
    assert os.uname().nodename=='4-gpu-vm'
    manifest=json.loads((R/'fixtures/MANIFEST.json').read_text())
    assert sha(R/'fixtures/MANIFEST.json')=='9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
    for case in ['integer','fractional','affine','noisy']:
        for name,value in manifest['cases'][case]['files'].items():assert sha(R/'fixtures'/name)==value
    write(L/'input-binding.json',manifest)
    run('oracle-controls',[P,str(R/'replay.py'),'--controls',str(R/'controls.json')],env=env)
    gpu=lock('/tmp/motioncorr-gpu3-correctness.lock')
    try:
        bench=lock('/tmp/motioncorr-bench.lock');fcntl.flock(bench,fcntl.LOCK_UN);bench.close()
        write(L/'locks.json',dict(gpu_lock=gpu.name,pid=os.getpid(),utc=now(),mode='exclusive nonblocking through final health',bench_probe='acquired then released',build='already completed and released'))
        health('preflight',idle=True)
        try:
            for case in ['integer','fractional','affine','noisy']:
              for backend in ['cpu','cuda']:
                for enabled in [False,True]:
                    label=f'{backend}-{case}-'+('on' if enabled else 'off');d=R/'runs'/label;d.mkdir();(d/'state').mkdir();(d/'capture').mkdir()
                    if backend=='cuda':health('before-'+label,idle=True)
                    arm_env=dict(env,MC_CCF_STATE=str(d/'state'))
                    if enabled:
                        arm_env['MC_CCF_CAPTURE']=str(d/'capture')
                        if case in ['affine','noisy']:arm_env['MC_CCF_PATCH']='2,1' if case=='affine' else '1,3'
                    p='3' if case in ['affine','noisy'] else '1';binary=R/('build-'+backend)/'motioncorr'
                    argv=[str(binary),'--i',case+'.star','--o',str(d/'out'),'--use_own','--j','1','--patch_x',p,'--patch_y',p,'--bin_factor','1','--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum','5','--skip_logfile']
                    if backend=='cuda':argv+=['--gpu','0']
                    assert launches<16;launches+=1;write(L/'launch-count.json',dict(started=launches,maximum=16,last=label))
                    run(label,argv,env=arm_env,cwd=R/'fixtures')
                    if backend=='cuda':health('after-'+label)
                    assert (d/'state/global.txt').is_file() and (d/'state/model.txt').is_file()
                    if enabled:assert list((d/'capture').glob('*.json'))
                    run('check-'+label,[P,str(R/'src/tools/check_motion_diagnostics.py'),'--fixtures',str(R/'fixtures'),'--case',case,'--candidate',str(d/'out'/f'{case}.star'),'--summed-image',str(d/'out'/f'{case}.mrc'),'--json',str(d/'checker.json')],env=env,expected=(1,))
                neutral(case,backend)
        finally:
            util=health('final-health')
            for sample in range(3):
                if not util:break
                time.sleep(1);util=health('final-settle-'+str(sample+1))
            assert util==0,'UNRUN final idle not established'
            write(L/'release-health.json',dict(status='PASS',utc=now(),pid=os.getpid(),gpu_uuid=U,lock_held=True))
    finally:
        fcntl.flock(gpu,fcntl.LOCK_UN);gpu.close();write(L/'released.json',dict(utc=now(),pid=os.getpid(),gpu_uuid=U))
    write(R/'campaign.json',dict(status='PASS',application_processes=launches,neutral_pairs=len(pairs),truth='all selected gates remain FAIL'))
rc=0
try:main()
except Exception as e:print(repr(e),flush=True);rc=1
(R/'run.exit').write_text(str(rc)+'\n');sys.exit(rc)
