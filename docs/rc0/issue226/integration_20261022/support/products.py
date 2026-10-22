"""Bounded QM run: one e10216 reference and 8/8.5/8.75 GiB neighbours."""
import fcntl, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from health import W, UUID, snapshot, settle, remember, stop_owned
SPECS=['e10216-L-auto@none','e10216-L-auto@8','e10216-L-auto@8.5','e10216-L-auto@8.75']
INPUT=Path('/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/data/EMPIAR-10216/data/FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrc')
EXPECTED='f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56'

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''): h.update(b)
    return h.hexdigest()

def main():
    assert (W/'logs/native.exit').read_text().strip()=='0'
    gpu=open('/tmp/motioncorr-gpu3-correctness.lock','w'); fcntl.flock(gpu,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def bench():
        with open('/tmp/motioncorr-bench.lock','w') as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    bench(); snapshot('products-pre',idle=True); bench()
    ram=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
    disk=shutil.disk_usage(W).free
    if ram<32*(1<<30) or disk<40*(1<<30): raise RuntimeError('insufficient RAM/scratch for bounded e10216')
    assert INPUT.stat().st_size==1979712512 and sha(INPUT)==EXPECTED
    originals={
        'balloon':Path('/mnt/clathrin/alex-motioncorr-rc0/W-QM/balloon'),
        'qm_balloon.cu':Path('/mnt/clathrin/alex-motioncorr-rc0/W-QM/qm_balloon.cu')}
    expected={'balloon':'3ede9c4fec56c3fbbae9a31b1bd75ed4abf01fab353f7b92e701fdb1f9747686',
              'qm_balloon.cu':'486bfe4e361c3c2e7c1dd2298153a2d10721f3224aa5768ef95e72d477c13cd8'}
    for name,p in originals.items():
        if sha(p)!=expected[name]: raise RuntimeError('balloon identity changed')
        target=W/name
        if target.exists(): raise RuntimeError('refusing to overwrite preparation')
        shutil.copy2(p,target)
        assert sha(target)==expected[name]
    for s in SPECS:
        if (W/'runs'/s).exists(): raise RuntimeError('run already exists: '+s)
    prov={'source':'fe104f217703871c897887a9b7ca3a6bff4b7b69','input':str(INPUT),
          'input_sha256':EXPECTED,'input_bytes':INPUT.stat().st_size,'available_ram_bytes':ram,
          'available_scratch_bytes':disk,'cpus':sorted(os.sched_getaffinity(0)),
          'environment':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','CUDA_VISIBLE_DEVICES')},
          'files':{str(p):sha(p) for p in [W/'balloon',W/'qm_balloon.cu',W/'support/qm_batch.py',W/'src/docs/issue85_laneC/compare_output_trees.py',W/'src/docs/rc0/qual_qm_vram/harness/qm_batch.py',W/'src/docs/workload_corpus/families.json',W/'build/motioncorr']}}
    (W/'logs/product-provenance.json').write_text(json.dumps(prov,indent=2)+'\n')
    spec=importlib.util.spec_from_file_location('qm_adapted',W/'support/qm_batch.py')
    qm=importlib.util.module_from_spec(spec); spec.loader.exec_module(qm)
    original_popen=subprocess.Popen
    active=[]; faults=[]
    def tracked_popen(*args,**kwargs):
        p=original_popen(*args,**kwargs)
        argv=args[0] if args else kwargs.get('args')
        if isinstance(argv,list) and str(argv[0]) in (str(W/'balloon'),'/usr/bin/time'):
            remember(p); active.append(p)
            with (W/'logs/native-launches.jsonl').open('a') as f:
                f.write(json.dumps({'argv':argv,'pid':p.pid,'cwd':str(kwargs.get('cwd',W))})+'\n')
        return p
    subprocess.Popen=tracked_popen
    original_smi=qm.smi
    def checked_smi(query):
        try: snapshot('qm-sample')
        except BaseException as e:
            faults.append(repr(e))
            for p in list(active): stop_owned(p)
            raise
        return original_smi(query)
    qm.smi=checked_smi
    def stop_balloon(self):
        if self.p is not None:
            stop_owned(self.p)
            self.p=None; self.held=0
    qm.Balloon.stop=stop_balloon
    def no_wait_bench(): bench(); return 0
    qm.wait_bench_lock=no_wait_bench
    results=[]
    try:
        for s in SPECS:
            snapshot(s+'-pre',idle=True); bench()
            print('RUN',s,flush=True)
            r=qm.run_case(s,qm.families())
            r['binary_sha256']=prov['files'][str(W/'build/motioncorr')]
            results.append(r)
            (W/'logs/product-results.json').write_text(json.dumps(results,indent=2)+'\n')
            print(qm.summ(r),flush=True)
            settle(s)
            if faults: raise RuntimeError('hardware/ownership sampling failed: '+str(faults))
            if not r['all_products'] or not r['joint_star'] or r['gpu_apps_after'] or not r['balloon_gone']:
                text=(W/'runs'/s/'stdout.txt').read_text(errors='replace')
                named='ERROR: Out of GPU memory for ' in text and 'Refusing before host preprocessing.' in text
                product_files=[str(p.relative_to(W/'runs'/s/'out')) for p in (W/'runs'/s/'out').rglob('*') if p.suffix in ('.mrc','.star')]
                (W/'logs/refusal-or-failure.json').write_text(json.dumps({'spec':s,'named_early_refusal':named,'product_files':product_files,'exit':r['exit'],'result':r},indent=2)+'\n')
                raise RuntimeError('named admission refusal/design conflict' if named and not product_files else 'unexpected runner/publication/cleanup failure')
            if r['target_free_gib'] is not None and r.get('compare',{}).get('products_rc')!=0:
                raise RuntimeError('strict MRC/STAR product comparator failed')
    finally:
        for p in active: stop_owned(p)
        settle('products-final')
    fcntl.flock(gpu,fcntl.LOCK_UN); gpu.close()

if __name__=='__main__':
    (W/'logs/products.pid').write_text(str(os.getpid())+'\n')
    (W/'logs/products.started').write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())+'\n')
    rc=0
    try: main()
    except BaseException:
        import traceback; traceback.print_exc(); rc=1
    (W/'logs/products.exit').write_text(str(rc)+'\n')
    (W/'logs/products.finished').write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())+'\n')
    sys.exit(rc)
