#!/usr/bin/env python3
"""Predetermined same-state operator crosses. No candidate or product replacement."""
import fcntl,json,os,pathlib,subprocess,time
import resource_helpers as h
R=h.R
locks=[]
for p in ['/tmp/motioncorr-cuda-boundary-cpu80-87.lock','/tmp/motioncorr-gpu2-correctness.lock']:
 f=open(p,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
with open('/tmp/motioncorr-bench.lock','a') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
root=R/'inverse-repair-v2';root.mkdir(exist_ok=False);binary=R/'replay-v2-zero-fill';binary_sha=h.sha(binary)
(root/'PINS.json').write_text(json.dumps({'binary':str(binary),'binary_sha256':binary_sha,'source_sha256':h.sha(R/'replay-v2.cu'),'core_source':'7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd','harness_sha256':h.sha(__file__),'resource_helper_sha256':h.sha(h.__file__),'core_binary':json.loads((R/'diagnostic-pins.json').read_text()),'normalization':'forward FwdOnly 1/N; inverse unscaled','FFTW':'single plan thread, FFTW_ESTIMATE cached by alignment; no fftwf thread init; OMP outer8','layout':'rowmajor half-spectrum [cy,cx/2+1] complex64; real [cy,cx] float32','native_forward':'actual CudaMovieSession, batch1 per frame original24-frame allocation','native_inverse':'rank2 C2R batch24; native projection on scratch; packed distances'},indent=2)+'\n')
def run(case,name,mode,inp,backend):
 d=root/(case+'-'+name+'-'+backend);d.mkdir();out=d/'data';out.mkdir()
 expected={p.name:h.sha(p) for p in inp.iterdir() if p.is_file()}
 pre=h.admission(case,binary,binary_sha);pre['input_hashes']=expected;pre['input_directory']=str(inp)
 (d/'ADMISSION.json').write_text(json.dumps(pre,indent=2)+'\n')
 if not pre['admitted']:raise SystemExit('replay admission declined; retained, no launch/retry')
 env=os.environ.copy();env.pop('MC_BOUNDARY_DIR',None);env.update(OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='1',LD_LIBRARY_PATH='/usr/local/cuda-12.8/lib64',CUDA_VISIBLE_DEVICES=h.UUID if backend=='cuda' else '',CUDA_DEVICE_ORDER='PCI_BUS_ID')
 argv=[str(binary),mode,str(inp),str(out),backend]
 rec={'start':h.now(),'argv':argv,'env':{k:env[k] for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER']},'binary_sha256':binary_sha,'input_hashes':expected,'input_directory':str(inp),'affinity':h.affinity(os.getpid()),'device_samples':[],'child_affinities':[]}
 (d/'START.json').write_text(json.dumps(rec,indent=2)+'\n')
 with (d/'stdout.txt').open('w') as f:
  c=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,env=env)
  while c.poll() is None:
   for pid in h.tree(c.pid):
    try:
     for t in pathlib.Path(f'/proc/{pid}/task').iterdir():rec['child_affinities'].append({'pid':pid,'tid':int(t.name),'mask':h.affinity(t.name)})
    except (FileNotFoundError,ProcessLookupError):pass
   smi=h.cmd(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader']);rec['device_samples'].append(smi);time.sleep(.2)
 rec.update(rc=c.returncode,end=h.now(),output_hashes={p.name:h.sha(p) for p in out.iterdir() if p.is_file()},input_unchanged=all(h.sha(inp/p)==v for p,v in expected.items()))
 (d/'RUN.json').write_text(json.dumps(rec,indent=2)+'\n');print(d.name,c.returncode,flush=True)
 if c.returncode or not rec['input_unchanged']:raise SystemExit('replay failed; retained')
 if not rec['child_affinities'] or any(x['mask']!=list(range(80,88)) for x in rec['child_affinities']):raise SystemExit('replay affinity witness incomplete; retained')
 return out
for case in ['00021','00046']:
 for stored in ['cpu','cuda']:
  inp=R/'capture'/f'{case}-G-{stored}'/'capture'
  native_inverse=run(case,f'inverse-{stored}','inverse',inp,'cuda')
  common=root/(case+'-common-projected-'+stored);common.mkdir()
  (common/'geometry.txt').symlink_to(inp/'geometry.txt')
  for f in [0,4]:(common/f'spectrum-{f}.c64').symlink_to(native_inverse/f'projected-spectrum-{f}.c64')
  run(case,f'inverse-projected-{stored}','inverse',common,'cpu')
  valid=run(case,f'inverse-valid-{stored}','inverse-valid',common,'cuda')
  assert (valid/'projection-noop.txt').read_text()=='PASS\n'
  assert all(h.sha(valid/f'projected-spectrum-{f}.c64')==h.sha(common/f'spectrum-{f}.c64') for f in [0,4])
(root/'COMPLETE').write_text(h.now()+'\n')
