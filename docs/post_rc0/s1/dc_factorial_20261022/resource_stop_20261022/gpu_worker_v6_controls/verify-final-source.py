import fcntl, hashlib, json, os, shutil, subprocess, sys, time, uuid
from pathlib import Path
repo=Path.cwd(); tools=repo/'docs/post_rc0/s1/dc_factorial_20261022/tools'
ns=Path('/tmp')/('motioncorr-dc262-v6-sol-static-'+str(uuid.uuid4())); ns.mkdir()
lease=open(ns/'.lease','a'); fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',TMPDIR=str(ns))
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
source=subprocess.run(['git','rev-parse','HEAD'],text=True,capture_output=True,check=True).stdout.strip()
ps=subprocess.run(['ps','-axo','pid=,ppid=,uid=,command='],text=True,capture_output=True,check=True).stdout
by={}
for line in ps.splitlines():
    f=line.split(None,3)
    if len(f)==4: by[int(f[0])]=dict(pid=int(f[0]),ppid=int(f[1]),uid=int(f[2]),cmd=f[3])
chain=[]; pid=os.getpid()
while pid in by and pid not in [r['pid'] for r in chain]:
    row=by[pid]; chain.append(row); pid=row['ppid']
# Store just identities/provider commands; the shell's multiline script text is not needed.
ancestry=[dict(pid=r['pid'],ppid=r['ppid'],uid=r['uid'],cmd=r['cmd'][:250]) for r in chain]
rec=dict(schema='dc262-v6-static-attempt/1',namespace=str(ns),uuid=ns.name.rsplit('static-',1)[1],source_sha=source,
    utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),python=sys.version,load=os.getloadavg(),logical_cpus=os.cpu_count(),
    affinity='UNAVAILABLE: macOS has no sched_getaffinity; no pinning applied',numeric_threads=1,scratch_cap_bytes=256*1024**2,
    lifetime_lease='nonblocking flock acquired',ancestry=ancestry,old_author_is_ancestor=23920 in [x['pid'] for x in chain],
    real_worker_suite='UNRUN: frozen --resume owner binding unavailable in Codex ancestry; not invoked, no spoofing',
    matching_live_controls=[r for r in by.values() if any(x in r['cmd'] for x in ['test_gpu_worker_v6.py --','run_v6_controls.py --'])],
    source_hashes={p.name:sha(p) for p in tools.iterdir() if p.name in ['gpu_worker_v6.py','test_gpu_worker_v6.py','run_v6_controls.py','test_run_v6_admission.py','test_v6_static.py','v6_mutants.json']},commands=[])
(ns/'PREFLIGHT.json').write_text(json.dumps(rec,indent=1)+'\n')
py='/Users/alex.konstantinov/.local/bin/python3'
def run(name,args):
    cmd=[py,'-B']+args
    with open(ns/(name+'.out'),'w') as f:
        p=subprocess.run(cmd,cwd=repo,stdout=f,stderr=subprocess.STDOUT,timeout=180)
    rec['commands'].append(dict(name=name,argv=cmd,exit=p.returncode))
    return p.returncode
assert run('static-units',[str(tools/'test_v6_static.py'),'--json',str(ns/'static-units.json')]) == 0, 'stop on baseline failure'
run('admission-units',[str(tools/'test_run_v6_admission.py'),'--json',str(ns/'admission-units.json')])
run('K28-K30',[str(tools/'test_gpu_worker_v6.py'),'--only','K28,K30','--json',str(ns/'K28-K30.json')])
# Compile every mutant, and retain fresh data-only checks on R4 targets. Never invoke the real-worker runner.
mutants=json.loads((tools/'v6_mutants.json').read_text()); src=(tools/'gpu_worker_v6.py').read_text(); checks=[]
for name,spec in mutants.items():
    text=src
    for old,new in spec['replace']:
        assert text.count(old)==1,(name,text.count(old)); text=text.replace(old,new)
    compile(text,name,'exec')
    row=dict(name=name,single_site=len(spec['replace'])==1,unique_targets=True,compiled=True,real_control='UNRUN')
    if name in ['initial_branch_root_signal_removed','loop_branch_root_signal_removed','errors_branch_root_signal_removed',
                'root_only_no_group','unguarded_hold_receipt','record_write_unchecked','jobstage_before_cleanup','no_activation_final','no_sighup_handler']:
        # Keep imports next to original campaign/helper, without creating untracked source in the repository.
        path=ns/(name+'.py'); path.write_text(text)
        # find_ownership searches parents: supply frozen in-repo dependencies in this isolated scratch tree.
        (ns/'tools/multi_gpu').mkdir(parents=True,exist_ok=True)
        shutil.copy2(repo/'tools/multi_gpu/process_ownership.py',ns/'tools/multi_gpu/process_ownership.py')
        shutil.copy2(tools/'campaign.py',ns/'campaign.py')
        code=run('static-mutant-'+name,[str(tools/'test_v6_static.py'),'--worker',str(path),'--json',str(ns/('static-mutant-'+name+'.json'))])
        row.update(data_only_exit=code,data_only_rejected=code==1,mutant_sha256=sha(path))
    checks.append(row)
(ns/'MUTANTS.json').write_text(json.dumps(checks,indent=1)+'\n')
rec.update(end_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),end_load=os.getloadavg(),
    scratch_bytes=sum(p.stat().st_size for p in ns.rglob('*') if p.is_file()))
assert rec['scratch_bytes']<rec['scratch_cap_bytes']
(ns/'ATTEMPT.json').write_text(json.dumps(rec,indent=1)+'\n')
Path('/tmp/dc262-v6-static-last.json').write_text(json.dumps(dict(namespace=str(ns),source_sha=source),indent=1)+'\n')
print(json.dumps(dict(namespace=str(ns),source_sha=source,commands=rec['commands'],scratch_bytes=rec['scratch_bytes']),indent=1))
