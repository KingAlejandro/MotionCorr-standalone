#!/usr/bin/env python3
"""Eight inverse-only jobs on DC-only copies of four frozen valid sets."""
import fcntl,hashlib,inspect,json,os,pathlib,shutil,subprocess,sys,time
import numpy as np
import dc_resources as h
P=pathlib.Path(__file__).parent
pins=json.loads((P/'FROZEN-PINS.json').read_text());root=pathlib.Path(pins['namespace']);base=h.R
binary=pathlib.Path(pins['fixed_replay_binary']);bsha=pins['fixed_replay_binary_sha256']
locks=[]
for p in ['/tmp/motioncorr-cuda-boundary-cpu80-87.lock','/tmp/motioncorr-gpu2-correctness.lock']:
 f=open(p,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
with open('/tmp/motioncorr-bench.lock','a') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert h.affinity(os.getpid())==list(range(80,88))
assert h.sha(binary)==bsha
assert h.sha(base/'replay-v2.cu')==pins['fixed_replay_source_sha256']
root.mkdir(exist_ok=False)
(root/'FROZEN-PINS.json').write_bytes((P/'FROZEN-PINS.json').read_bytes())
(root/'PLAN.md').write_bytes((P/'PLAN.md').read_bytes())
import numpy.fft._pocketfft as fft, numpy.fft._pocketfft_umath as nativefft
assert np.__version__==pins['numpy_version'] and h.sha(fft.__file__)==pins['numpy_pocketfft_python_sha256']
envpin={'python':sys.version,'python_executable':sys.executable,'numpy':np.__version__,'numpy_path':np.__file__,'pocketfft_source':fft.__file__,'pocketfft_source_sha256':h.sha(fft.__file__),'pocketfft_extension':nativefft.__file__,'pocketfft_extension_sha256':h.sha(nativefft.__file__),'irfft2_signature':str(inspect.signature(np.fft.irfft2)),'raw_fft_source':inspect.getsource(fft._raw_fft),'irfftn_source':inspect.getsource(fft.irfftn),'swap_direction_source':inspect.getsource(fft._swap_direction),'native_normalizer':'inverse norm=forward swaps to backward; factor1 per axis','replay_binary_sha256':bsha,'replay_source_sha256':h.sha(base/'replay-v2.cu'),'harness_sha256':h.sha(__file__),'resource_helper_sha256':h.sha(h.__file__),'preregistered_commit':'d10045e5cd4324eba62e189e5ffd256b42399557'}
(root/'ENVIRONMENT.json').write_text(json.dumps(envpin,indent=2)+'\n')
expected={binary:bsha,base/'replay-v2.cu':pins['fixed_replay_source_sha256']};inputs=[]
for case in ['00021','00046']:
 for source in ['cpu','cuda']:
  name=case+'-'+source;original=base/'inverse-repair-v2'/(case+'-common-projected-'+source)
  raw=root/'original-copies'/name;zero=root/'zero-dc-copies'/name;raw.mkdir(parents=True);zero.mkdir(parents=True)
  assert h.sha(original/'geometry.txt')==pins['geometry_sha256']
  for dest in [raw,zero]:shutil.copyfile(original/'geometry.txt',dest/'geometry.txt')
  row={'case':case,'source':source,'source_directory':str(original),'original_copy':str(raw),'zero_dc_copy':str(zero),'files':{}}
  for frame in [0,4]:
   filename=f'spectrum-{frame}.c64';src=original/filename;frozen=next(x for x in pins['maps'] if x['case']==case and x['source']==source and x['frame']==frame)['valid_spectrum_sha256']
   assert h.sha(src)==frozen;data=src.read_bytes();assert len(data)==972*487*8
   a=np.frombuffer(data,dtype='<c8').reshape(972,487);assert np.isfinite(a).all() and a[0,0].imag==0
   def valid(z):return all(np.array_equal(z[:,x],np.conj(z[(-np.arange(972))%972,x])) for x in [0,486])
   assert valid(a)
   changed=b'\0'*8+data[8:];(raw/filename).write_bytes(data);(zero/filename).write_bytes(changed)
   za=np.frombuffer(changed,dtype='<c8').reshape(a.shape);assert valid(za) and za[0,0]==0 and changed[8:]==data[8:]
   expected[src]=frozen;expected[raw/filename]=frozen;expected[zero/filename]=h.sha(zero/filename)
   before={b:base/'inverse-repair-v2'/(case+('-inverse-projected-' if b=='cpu' else '-inverse-valid-')+source+'-'+b)/'data'/f'map-{frame}.f32' for b in ['cpu','cuda']}
   row['files'][frame]={'original_sha256':frozen,'zero_dc_sha256':expected[zero/filename],'bytes':len(data),'original_DC_real':float(a[0,0].real),'original_DC_imag':float(a[0,0].imag),'only_first8bytes_changed':True,'Hermitian_before_after':True,'baseline_maps':{b:{'path':str(p),'sha256':h.sha(p)} for b,p in before.items()}}
   for b,p in before.items():expected[p]=row['files'][frame]['baseline_maps'][b]['sha256']
  expected[original/'geometry.txt']=pins['geometry_sha256'];expected[raw/'geometry.txt']=pins['geometry_sha256'];expected[zero/'geometry.txt']=pins['geometry_sha256']
  inputs.append(row)
(root/'INPUTS.json').write_text(json.dumps(inputs,indent=2)+'\n')
for item in inputs:
 case=item['case'];source=item['source'];inp=pathlib.Path(item['zero_dc_copy'])
 for backend in ['cpu','cuda']:
  d=root/'runs'/(case+'-'+source+'-'+backend);d.mkdir(parents=True);out=d/'data';out.mkdir()
  pre=h.admission(binary,bsha,expected);(d/'ADMISSION.json').write_text(json.dumps(pre,indent=2)+'\n')
  if not pre['admitted']:raise SystemExit('fresh admission declined; no launch/retry')
  env=os.environ.copy();env.pop('MC_BOUNDARY_DIR',None);env.update(OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='1',LD_LIBRARY_PATH='/usr/local/cuda-12.8/lib64',CUDA_VISIBLE_DEVICES=h.UUID if backend=='cuda' else '',CUDA_DEVICE_ORDER='PCI_BUS_ID')
  argv=[str(binary),'inverse' if backend=='cpu' else 'inverse-valid',str(inp),str(out),backend]
  rec={'start':h.now(),'argv':argv,'binary_sha256':bsha,'fixed_source':pins['fixed_replay_source'],'case':case,'source':source,'backend':backend,'input_hashes':{str(x):v for x,v in expected.items()},'env':{k:env[k] for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER']},'parent_affinity':h.affinity(os.getpid()),'child_affinities':[],'device_samples':[]}
  (d/'START.json').write_text(json.dumps(rec,indent=2)+'\n')
  with (d/'stdout.txt').open('w') as stream:
   child=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,env=env)
   rec['child_pid']=child.pid
   while child.poll() is None:
    for pid in h.tree(child.pid):
     try:
      for tid in pathlib.Path(f'/proc/{pid}/task').iterdir():rec['child_affinities'].append({'pid':pid,'tid':int(tid.name),'mask':h.affinity(tid.name)})
     except (FileNotFoundError,ProcessLookupError):pass
    rec['device_samples'].append(h.cmd(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader']));time.sleep(.1)
  rec.update(rc=child.returncode,end=h.now(),output_hashes={p.name:h.sha(p) for p in out.iterdir() if p.is_file()},all_frozen_files_unchanged=all(h.sha(p)==v for p,v in expected.items()))
  if backend=='cuda':
   rec['projection_noop']=(out/'projection-noop.txt').read_text()=='PASS\n'
   rec['projected_bytes_identical']=all(h.sha(out/f'projected-spectrum-{f}.c64')==h.sha(inp/f'spectrum-{f}.c64') for f in [0,4])
   rec['own_GPU2_witness']=any(line.split(',')[0].strip()==str(child.pid) and line.split(',')[1].strip()==h.UUID for smi in rec['device_samples'] for line in smi.splitlines() if ',' in line)
  (d/'RUN.json').write_text(json.dumps(rec,indent=2)+'\n');print(d.name,rec['rc'],flush=True)
  assert rec['rc']==0 and rec['all_frozen_files_unchanged']
  assert rec['child_affinities'] and all(x['mask']==list(range(80,88)) for x in rec['child_affinities'])
  if backend=='cuda':assert rec['projection_noop'] and rec['projected_bytes_identical'] and rec['own_GPU2_witness']
(root/'COMPLETE').write_text(h.now()+'\n')
(root/'FINAL-GPU.txt').write_text(h.cmd(['nvidia-smi','-q']))
(root/'FINAL-SPACE.txt').write_text(h.cmd(['du','-sb',str(base)]))
