#!/usr/bin/env python3
"""Analysis only: no FFT, producer, image-pixel, fitting, or repository writes."""
import os
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']: os.environ[k]='1'
import pathlib,json,hashlib,datetime,math,sys
import numpy as np
S=pathlib.Path(__file__).resolve().parent; D=S/'data'; E=S/'sealed/evidence'; R=S/'receipts/inverse-repair-v2'
HEAD='0ba72a7197933f5f0c7149491853c04b0d780013'; ROOT='/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026/'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
idx=load(E/'verified-file-index.json'); index={v['path']:v for v in idx}; assert len(index)==len(idx)==882
sealed=load(E/'inverse-v2-analysis.json'); old=load(E/'replay-v1-analysis-original.json')
checks={}; diffs=[]; comparisons=[]
def compare(actual,expected,path):
 if isinstance(expected,dict):
  for k,v in expected.items():compare(actual[k],v,path+'/'+k)
 elif isinstance(expected,list):
  assert len(actual)==len(expected),path
  for i,(a,b) in enumerate(zip(actual,expected)):compare(a,b,path+'/'+str(i))
 elif isinstance(expected,(int,float)) and not isinstance(expected,bool):
  delta=abs(float(actual)-float(expected));comparisons.append({'path':path,'abs_delta':delta})
  if not math.isfinite(float(actual)) or delta>1e-12:diffs.append({'path':path,'actual':actual,'sealed':expected,'abs_delta':delta})
 elif actual!=expected:diffs.append({'path':path,'actual':actual,'sealed':expected})
def array(p,dtype,shape):
 a=np.fromfile(p,dtype=dtype);assert a.size==math.prod(shape),str(p);a=a.reshape(shape);assert np.isfinite(a).all(),str(p);return a
def stats(a,b):
 assert a.shape==b.shape and a.dtype==b.dtype==np.dtype('<f4')
 d=b.astype('float64')-a.astype('float64')
 return {'count':int(a.size),'different_bits':int(np.count_nonzero(a.view('<u4')!=b.view('<u4'))),'rmse':float(np.sqrt(np.mean(d*d))),'max_abs':float(np.max(np.abs(d)))}
def herm(a):
 # Packed R2C imposes conjugacy on kx=0 and even-nx Nyquist columns.
 vals=[];corners=[]
 for x in [0,a.shape[1]-1]:
  col=a[:,x];vals.append(float(np.max(np.abs(col-np.conj(col[(-np.arange(len(col)))%len(col)])))))
  corners.extend([float(a[0,x].imag),float(a[a.shape[0]//2,x].imag)])
 return {'column_max_conjugacy_error':vals,'valid':all(v==0 for v in vals),'self_conjugate_corner_imaginary':corners}
def peak(a,g):
 # Enumerate signed search coordinates in y,x order, wrapping array indices.
 r=int(g['search_range']); candidates=[(float(a[y%a.shape[0],x%a.shape[1]]),x,y) for y in range(-r,r+1) for x in range(-r,r+1)]
 mx=max(t[0] for t in candidates); winners=[t for t in candidates if t[0]==mx];_,x,y=winners[0]
 def sample(x,y):return float(a[y%a.shape[0],x%a.shape[1]])
 def off(plus,minus):
  den=plus+minus-2*mx
  return -0.5*(plus-minus)/den if abs(den)>1e-15 else 0.0
 return {'integer':[x,y],'ties':len(winners),'shift_px':[(x+off(sample(x+1,y),sample(x-1,y)))*g['nx']/g['ccf_nx'],(y+off(sample(x,y+1),sample(x,y-1)))*g['ny']/g['ccf_ny']],'max':mx}
def vectors(d):return {'rms':float(np.sqrt(np.mean(np.sum(d*d,axis=-1)))),'max_vector':float(np.max(np.sqrt(np.sum(d*d,axis=-1)))),'max_component':float(np.max(np.abs(d)))}
# Reverify every fetched array against sealed index, independent of fetch.py.
fetched=[]
for p in (S/'fetch-list.txt').read_text().splitlines():
 f=D/p;h=sha(f);assert f.stat().st_size==index[p]['bytes'] and h==index[p]['sha256'];fetched.append(p)
expected_dirs={f'{c}-{route}' for c in ['00021','00046'] for b in ['cpu','cuda'] for route in [f'inverse-{b}-cuda',f'inverse-projected-{b}-cpu',f'inverse-valid-{b}-cuda']}
runs={p.parent.name:load(p) for p in R.glob('*/RUN.json')}; admissions={p.parent.name:load(p) for p in R.glob('*/ADMISSION.json')}
assert set(runs)==set(admissions)==expected_dirs and len(runs)==12
receipt_details=[]
for name in sorted(expected_dirs):
 run=runs[name]; adm=admissions[name]; path=R/name/'RUN.json';start=datetime.datetime.fromisoformat(run['start']);at=datetime.datetime.fromisoformat(adm['utc'])
 assert run['rc']==0 and run['input_unchanged'] is True
 assert run['child_affinities'] and all(t['mask']==list(range(80,88)) for t in run['child_affinities'])
 assert adm['admitted'] is True and 0 <= (start-at).total_seconds() < 5
 assert not adm['overlap_lease_conflicts'] and not adm['compute_conflicts']
 assert run['argv'][1] in ['inverse','inverse-valid'] and run['argv'][2]==run['input_directory']
 assert run['argv'][3]==ROOT+f'inverse-repair-v2/{name}/data'
 out=run['argv'][3].removeprefix(ROOT)
 for n,h in run['output_hashes'].items():assert sha(D/out/n)==h and index[out+'/'+n]['sha256']==h
 # Every actual input attestation must agree with index if indexed. Canonical copies are bound below.
 inp=run['input_directory'].removeprefix(ROOT)
 for n,h in run['input_hashes'].items():
  if inp+'/'+n in index:assert index[inp+'/'+n]['sha256']==h
 receipt_details.append({'name':name,'run_sha256':sha(path),'admission_sha256':sha(path.with_name('ADMISSION.json')),'rc':run['rc'],'input_unchanged':True,'admission_to_start_seconds':(start-at).total_seconds(),'child_affinity_samples':len(run['child_affinities']),'argv':run['argv'],'input_hashes':run['input_hashes'],'output_hashes':run['output_hashes']})
checks.update({'12-inverse-only-exits-and-input-unchanged':True,'12-child-affinity':True,'12-fresh-admission':True})
map_rows=[];observations={};validity={};links=[]
for c in ['00021','00046']:
 caps={b:D/f'capture/{c}-G-{b}/capture' for b in ['cpu','cuda']}
 gs={b:{k:float(v) for k,v in (line.split() for line in (caps[b]/'geometry.txt').read_text().splitlines())} for b in caps};assert gs['cpu']==gs['cuda'];g=gs['cpu'];shape=(int(g['ccf_ny']),int(g['ccf_nx']));specshape=(shape[0],shape[1]//2+1)
 assert shape[0]%2==shape[1]%2==0 and int(g['nframes'])==24
 for b in ['cpu','cuda']:
  label=f'{c}-{b}';z=sealed['cases'][c][b]
  names=[f'{c}-inverse-{b}-cuda',f'{c}-inverse-projected-{b}-cpu',f'{c}-inverse-valid-{b}-cuda']; compat,vcpu,vgpu=[D/f'inverse-repair-v2/{n}/data' for n in names]
  checks[label+'-projection-noop-marker']=(vgpu/'projection-noop.txt').read_bytes()==b'PASS\n'
  for f in [0,4]:
   fs=str(f);p=compat/f'projected-spectrum-{f}.c64';valid=array(p,'<c8',specshape);raw=array(caps[b]/f'spectrum-{f}.c64','<c8',specshape)
   vh=herm(valid);rh=herm(raw);validity[f'{label}-{f}']={'projected':vh,'raw':rh};compare({k:v for k,v in vh.items() if k!='self_conjugate_corner_imaginary'},z['projected_validity'][fs],f'/cases/{c}/{b}/projected_validity/{f}');compare({k:v for k,v in rh.items() if k!='self_conjugate_corner_imaginary'},z['raw_actual_input_is_Hermitian'][fs],f'/cases/{c}/{b}/raw_actual_input_is_Hermitian/{f}')
   checks[f'{label}-{f}-valid']=vh['valid'] and all(v==0 for v in vh['self_conjugate_corner_imaginary'])
   canonical=sha(p);assert canonical==z['same_valid_input_sha256'][fs]
   cpu_input=runs[names[1]]['input_hashes'][f'spectrum-{f}.c64'];gpu_input=runs[names[2]]['input_hashes'][f'spectrum-{f}.c64'];gpu_post=sha(vgpu/f'projected-spectrum-{f}.c64')
   checks[f'{label}-{f}-byteidentical-valid-input']=canonical==cpu_input==gpu_input==gpu_post
   links.append({'case':c,'stored':b,'frame':f,'canonical_sha256':canonical,'actual_cpu_input_sha256':cpu_input,'actual_cuda_input_sha256':gpu_input,'cuda_postprojection_sha256':gpu_post,'canonical_basis':'compat projected bytes + CPU/CUDA RUN input_hashes; common copy not independently fetched'})
   a=array(vcpu/f'map-{f}.f32','<f4',shape);v=array(vgpu/f'map-{f}.f32','<f4',shape);co=array(compat/f'map-{f}.f32','<f4',shape)
   metrics=stats(a,v);compare(metrics,z['maps'][fs]['same_valid_input_inverse'],f'/cases/{c}/{b}/maps/{f}/same_valid_input_inverse')
   same=stats(co,v);compare(same,z['maps'][fs]['rawCUDA_vs_validCUDA'],f'/cases/{c}/{b}/maps/{f}/rawCUDA_vs_validCUDA');checks[f'{label}-{f}-same-consumed-transform']=same['different_bits']==0
   peaks={'CPU':peak(a,g),'CUDA_byte_noop_projection_then_C2R':peak(v,g)}
   for backend,pk in peaks.items():compare(pk,z['projected_valid_peaks'][backend][fs],f'/cases/{c}/{b}/projected_valid_peaks/{backend}/{f}')
   assert peaks['CPU']['integer']==peaks['CUDA_byte_noop_projection_then_C2R']['integer'] and all(pk['ties']==1 for pk in peaks.values())
   row={'case':c,'stored':b,'frame':f,'geometry':g,'metrics':metrics,'peaks':peaks,'shift_cuda_minus_cpu_px':(np.array(peaks['CUDA_byte_noop_projection_then_C2R']['shift_px'])-np.array(peaks['CPU']['shift_px'])).tolist()};map_rows.append(row)
   if b=='cuda':
    native=array(caps[b]/f'map-{f}.f32','<f4',shape);nc=stats(native,co);compare(nc,z['maps'][fs]['native_capture_vs_v2'],f'/cases/{c}/{b}/maps/{f}/native_capture_vs_v2');checks[f'{label}-{f}-native-capture-selfreproduction']=nc['different_bits']==0
    checks[f'{label}-{f}-native-actual-IFFT-input']=sha(caps[b]/f'ifft-input-{f}.c64')==canonical
 # Actual recorded native scalar observations retain CPU f64 and CUDA f32 types.
 cpu=np.stack([array(caps['cpu']/f'peak-{axis}.f64','<f8',(24,)) for axis in ['x','y']],axis=1)
 gpu32=np.stack([array(caps['cuda']/f'peak-{axis}.f32','<f4',(24,)) for axis in ['x','y']],axis=1);gpu=gpu32.astype('float64')
 delta=gpu-cpu;mathanchor=(gpu-gpu[0])-(cpu-cpu[0]);nativeanchor=(gpu32-gpu32[0]).astype('float64')-(cpu-cpu[0])
 obs={'cpu_raw_px':cpu.tolist(),'cuda_raw_px':gpu.tolist(),'raw_cuda_minus_cpu_px':delta.tolist(),'raw_delta_vector_px':vectors(delta),'anchor_adjusted_delta_px':mathanchor.tolist(),'anchor_adjusted_delta_vector_px':vectors(mathanchor),'native_float_anchor_adjusted_delta_px':nativeanchor.tolist(),'native_float_anchor_delta_vector_px':vectors(nativeanchor),'common_frame0_delta_px':delta[0].tolist()}
 for k,v in obs.items():compare(v,old['cases'][c]['native_observations'][k],f'/v1/cases/{c}/native_observations/{k}')
 obs['anchoring_increases_difference']=vectors(mathanchor)['rms']>vectors(delta)['rms']; observations[c]=obs
assert set(checks)==set(sealed['controls']) and len(checks)==39
compare(checks,sealed['controls'],'/controls')
result={'reviewed_head':HEAD,'status':'CLEAR bounded numerical/result reporting' if all(checks.values()) and not diffs else 'FINDINGS','controls':checks,'strict_receipt_coverage':{'expected':12,'RUN':len(runs),'ADMISSION':len(admissions),'exact_same_directories':True},'receipt_details':receipt_details,'valid_input_links':links,'validity':validity,'same_valid_maps':map_rows,'native_observations':observations,'sealed_comparison_count':len(comparisons),'maximum_metric_abs_delta':max(x['abs_delta'] for x in comparisons),'differences':diffs,'fetched_files':len(fetched),'fetched_payload_bytes':sum(index[p]['bytes'] for p in fetched),'numpy_version':np.__version__,'unrun':['native/GPU/FFT/movie producers','independent inverse oracle','image-pixel/endpoint recomputation','full 882-file rehash','v1 old-map comparisons','new source review','scientific/truth/performance qualification']}
(S/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(result['status'],'39controls',sum(checks.values()),'diffs',len(diffs),'maxdelta',result['maximum_metric_abs_delta'])
for row in map_rows:print(row['case'],row['stored'],row['frame'],row['metrics'],row['peaks'])
for c,o in observations.items():print(c,*(o[k]['rms'] for k in ['raw_delta_vector_px','anchor_adjusted_delta_vector_px','native_float_anchor_delta_vector_px']))
if diffs:print(json.dumps(diffs,indent=2))
