#!/usr/bin/env python3
"""Frozen peak/conditioning ledger and independent float64 arithmetic CCF controls."""
import fcntl,hashlib,inspect,json,math,os,pathlib,sys
import numpy as np
import dc_resources as h
P=pathlib.Path(__file__).parent;pins=json.loads((P/'FROZEN-PINS.json').read_text());root=pathlib.Path(pins['namespace']);assert (root/'COMPLETE').exists()
lease=open('/tmp/motioncorr-cuda-boundary-cpu80-87.lock','a');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert h.affinity(os.getpid())==list(range(80,88))
assert np.__version__==pins['numpy_version']
inputs=json.loads((root/'INPUTS.json').read_text());envpin=json.loads((root/'ENVIRONMENT.json').read_text())
import numpy.fft._pocketfft as pocket,numpy.fft._pocketfft_umath as extension
assert h.sha(pocket.__file__)==envpin['pocketfft_source_sha256'] and h.sha(extension.__file__)==envpin['pocketfft_extension_sha256']
refs=root/'reference-and-postmap';refs.mkdir(exist_ok=False)
EPS=1e-15;e=np.finfo(np.float64).eps
checks={};data=[];outputs=[]
# Small analytic normalization, axis/sign/amplitude controls; no native process.
tiny=np.zeros((8,6),dtype=np.complex128);tiny[0,0]=1
checks['numpy_unnormalized_DC_one_exact']=np.array_equal(np.fft.irfft2(tiny,s=(8,10),axes=(-2,-1),norm='forward'),np.ones((8,10)))
tiny[:]=0;tiny[1,1]=1;yy,xx=np.meshgrid(np.arange(8),np.arange(10),indexing='ij');analytic=2*np.cos(2*np.pi*(yy/8+xx/10));analytic_diff=float(np.max(np.abs(np.fft.irfft2(tiny,s=(8,10),axes=(-2,-1),norm='forward')-analytic)));analytic_bound=128*e
checks['numpy_cosine_axis_sign_amplitude']=analytic_diff<=analytic_bound

def vector(d):
 a=np.asarray(d,dtype=np.float64);return {'xy_px':a.tolist(),'norm_px':float(np.linalg.norm(a))}
def ulp32(value):
 a=np.float32(value)
 if not np.isfinite(a):return None
 return max(float(np.nextafter(a,np.float32(np.inf),dtype=np.float32))-float(a),float(a)-float(np.nextafter(a,np.float32(-np.inf),dtype=np.float32)))
def peak(m,g,quantized=True):
 assert m.shape==(g['ccf_ny'],g['ccf_nx']) and np.isfinite(m).all()
 r=g['search_range'];coords=np.arange(-r,r+1);yy,xx=np.meshgrid(coords,coords,indexing='ij');v=m[yy%m.shape[0],xx%m.shape[1]];mx=float(v.max());indices=np.argwhere(v==mx);iy,ix=indices[0];y,x=int(coords[iy]),int(coords[ix]);c=float(m[y%m.shape[0],x%m.shape[1]])
 out={'integer':[x,y],'ties':int(len(indices)),'center':c,'axes':{},'shift_px':[],'all_map_zero':bool(np.all(m==0)),'all_map_finite':True}
 for axis,yp,xp,yn,xn,integer,scale in [('x',y,x+1,y,x-1,x,g['nx']/g['ccf_nx']),('y',y+1,x,y-1,x,y,g['ny']/g['ccf_ny'])]:
  vp=float(m[yp%m.shape[0],xp%m.shape[1]]);vn=float(m[yn%m.shape[0],xn%m.shape[1]]);d=vp+vn-2*c;n=vp-vn;deg=abs(d)<=EPS;offset=0 if deg else -.5*n/d
  u=ulp32(c) if quantized else None
  qenv=(.5*ulp32(vp)+.5*ulp32(vn)+ulp32(c)) if quantized else None
  out['axes'][axis]={'vp':vp,'vn':vn,'c':c,'N_vp_minus_vn':n,'D_vp_plus_vn_minus_2c':d,'denominator_status':'ZERO' if d==0 else ('DEGENERATE_EPS' if deg else 'NONDEGENERATE'),'offset':offset,'ULP32_center':u,'abs_D_in_ULP32_center':abs(d)/u if u and d!=0 else None,'cancellation_condition':(abs(vp)+abs(vn)+2*abs(c))/abs(d) if d!=0 else None,'map_quantization_D_envelope':qenv,'map_quantization_relative_D_envelope':qenv/abs(d) if qenv is not None and d!=0 else None}
  out['shift_px'].append((integer+offset)*scale)
 return out

def save(name,a):
 p=refs/name;assert not p.exists();np.asarray(a,dtype='<f8').tofile(p);outputs.append({'path':str(p),'dtype':'little-endian float64','shape':list(a.shape),'sha256':h.sha(p),'bytes':p.stat().st_size});return outputs[-1]
def herm(s):return all(np.array_equal(s[:,x],np.conj(s[(-np.arange(s.shape[0]))%s.shape[0],x])) for x in [0,s.shape[1]-1])
def l1(s):
 w=np.full(s.shape[1],2.,dtype=np.float64);w[[0,-1]]=1.;K=s.size
 return float(np.sum(np.abs(s)*w,dtype=np.float64))/(1-4*K*e)
def direct(s,y,x,ny,nx):
 ky=np.arange(ny,dtype=np.float64);ky[ky>ny//2]-=ny;kx=np.arange(nx//2+1,dtype=np.float64);phase=np.exp((2j*np.pi)*((ky[:,None]*y/ny)+(kx[None,:]*x/nx)));w=np.full(nx//2+1,2.);w[[0,-1]]=1.
 return float(np.real(np.sum(s*phase*w,dtype=np.complex128)))
for item in inputs:
 case=item['case'];source=item['source'];raw=pathlib.Path(item['original_copy']);zero=pathlib.Path(item['zero_dc_copy']);g={k:int(float(v)) for k,v in (l.split() for l in (raw/'geometry.txt').read_text().splitlines())};ny,nx=g['ccf_ny'],g['ccf_nx'];k=64*(math.ceil(math.log2(nx))+math.ceil(math.log2(ny))+1);gamma=k*e/(1-k*e)
 for f in [0,4]:
  name=f'{case}-{source}-f{f}';rec={'case':case,'source':source,'frame':f,'geometry':g,'backend':{}};frozen=item['files'][str(f)]
  a=np.fromfile(raw/f'spectrum-{f}.c64',dtype='<c8').reshape(ny,nx//2+1);z=np.fromfile(zero/f'spectrum-{f}.c64',dtype='<c8').reshape(a.shape)
  checks[name+'-finite-valid-original-and-zero']=bool(np.isfinite(a).all() and np.isfinite(z).all() and herm(a) and herm(z))
  checks[name+'-DC-only-byte-change']=(raw/f'spectrum-{f}.c64').read_bytes()[8:]==(zero/f'spectrum-{f}.c64').read_bytes()[8:] and z[0,0]==0 and h.sha(raw/f'spectrum-{f}.c64')==frozen['original_sha256'] and h.sha(zero/f'spectrum-{f}.c64')==frozen['zero_dc_sha256']
  dc=float(a[0,0].real);aa=a.astype(np.complex128);zz=z.astype(np.complex128)
  original=np.fft.irfft2(aa,s=(ny,nx),axes=(-2,-1),norm='forward');changed=np.fft.irfft2(zz,s=(ny,nx),axes=(-2,-1),norm='forward');assert original.dtype==changed.dtype==np.dtype('float64')
  p0=peak(original,g,False);p1=peak(changed,g,False);L0,L1=l1(aa),l1(zz);bound=gamma*(L0+L1)+8*e*(abs(dc)+float(np.max(np.abs(original)))+float(np.max(np.abs(changed))))
  residual=float(np.max(np.abs((original-changed)-dc)))
  checks[name+'-double-only-constant']=residual<=bound
  direct_errors={}
  for label,spec,m,p in [('original',aa,original,p0),('zero',zz,changed,p1)]:
   x,y=p['integer'];direct_errors[label]=[]
   for yy,xx in [(y,x),(y,x+1),(y,x-1),(y+1,x),(y-1,x)]:direct_errors[label].append({'yx':[yy,xx],'abs_error':abs(direct(spec,yy,xx,ny,nx)-float(m[yy%ny,xx%nx]))})
   checks[name+'-direct-sum-'+label]=all(v['abs_error']<=bound for v in direct_errors[label])
  rec['spectra']={'original_sha256':frozen['original_sha256'],'zero_DC_sha256':frozen['zero_dc_sha256'],'original_DC_real':dc,'original_DC_imag':float(a[0,0].imag),'only_first8bytes_changed':checks[name+'-DC-only-byte-change'],'Hermitian_original_zero':checks[name+'-finite-valid-original-and-zero']}
  rec['double_reference']={'api':"numpy.fft.irfft2(complex128,s=(972,972),axes=(-2,-1),norm='forward')",'normalizer':1,'kind':'arithmetic CCF reference, not motion truth','original':p0,'zero':p1,'zero_minus_original_peak':vector(np.array(p1['shift_px'])-p0['shift_px']),'integer_unchanged':p0['integer']==p1['integer'],'constant_shift_check':{'DC_real':dc,'eps64':e,'k':k,'gamma_k':gamma,'inflated_L1_original':L0,'inflated_L1_zero':L1,'bound':bound,'max_residual':residual,'envelope_status':'PASS' if residual<=bound else 'FAIL','bound_kind':'preregistered conservative epsilon/L1 stable-FFT envelope; not implementation-certified'},'direct_sum_checks':direct_errors,'outputs':{'original':save(name+'-double-original.f64',original),'zero':save(name+'-double-zero.f64',changed)}}
  for b in ['cpu','cuda']:
   oldpath=pathlib.Path(frozen['baseline_maps'][b]['path']);assert h.sha(oldpath)==frozen['baseline_maps'][b]['sha256'];newpath=root/'runs'/f'{case}-{source}-{b}'/'data'/f'map-{f}.f32'
   before=np.fromfile(oldpath,dtype='<f4').reshape(ny,nx);after=np.fromfile(newpath,dtype='<f4').reshape(ny,nx);pb=peak(before,g);pa=peak(after,g);post=before.astype(np.float64)-dc;pp=peak(post,g,False)
   den_same=all(pp['axes'][axis]['D_vp_plus_vn_minus_2c']==pb['axes'][axis]['D_vp_plus_vn_minus_2c'] and pp['axes'][axis]['N_vp_minus_vn']==pb['axes'][axis]['N_vp_minus_vn'] for axis in ['x','y'])
   post_delta=vector(np.array(pp['shift_px'])-pb['shift_px']);checks[name+'-'+b+'-postmap-retains-stencil']=den_same and pp['integer']==pb['integer'] and post_delta['norm_px']<=64*e*(1+float(np.linalg.norm(pb['shift_px'])))
   oldpin=next(v for v in pins['maps'] if v['case']==case and v['source']==source and v['frame']==f)
   checks[name+'-'+b+'-baseline-peak-reproduces-frozen']=pb['shift_px']==oldpin['baseline_'+('CPU' if b=='cpu' else 'CUDA')+'_xy_px']
   rec['backend'][b]={'before':pb,'after':pa,'integer_unchanged':pb['integer']==pa['integer'],'before_minus_double_reference':vector(np.array(pb['shift_px'])-p0['shift_px']),'after_minus_double_reference':vector(np.array(pa['shift_px'])-p1['shift_px']),'before_map':{'path':str(oldpath),'sha256':h.sha(oldpath)},'after_map':{'path':str(newpath),'sha256':h.sha(newpath)},'postmap_negative_control':{'arithmetic':'cast original float32 map to float64, subtract real stored DC; no FFT','peak':pp,'minus_original_peak':post_delta,'stencil_D_and_N_exactly_preserved':den_same,'inherited_original_ULP32':{axis:pb['axes'][axis]['ULP32_center'] for axis in ['x','y']},'minus_original_double_reference':vector(np.array(pp['shift_px'])-p0['shift_px']),'output':save(name+'-'+b+'-postmap-negative.f64',post)}}
  rec['CPU_CUDA_before']=vector(np.array(rec['backend']['cuda']['before']['shift_px'])-rec['backend']['cpu']['before']['shift_px']);rec['CPU_CUDA_after']=vector(np.array(rec['backend']['cuda']['after']['shift_px'])-rec['backend']['cpu']['after']['shift_px']);data.append(rec)
anchored=[]
for case in ['00021','00046']:
 for source in ['cpu','cuda']:
  f0=next(x for x in data if x['case']==case and x['source']==source and x['frame']==0);f4=next(x for x in data if x['case']==case and x['source']==source and x['frame']==4)
  row={'case':case,'source':source}
  for state in ['before','after']:
   values={b:np.array(f4['backend'][b][state]['shift_px'])-f0['backend'][b][state]['shift_px'] for b in ['cpu','cuda']};row[state]={b:vector(v) for b,v in values.items()};row[state]['CUDA_minus_CPU']=vector(values['cuda']-values['cpu'])
  anchored.append(row)
maxbefore=max(x['CPU_CUDA_before']['norm_px'] for x in data);maxafter=max(x['CPU_CUDA_after']['norm_px'] for x in data);ratio=maxafter/maxbefore if maxbefore else None
checks['baseline-max-exactly-frozen']=maxbefore==pins['original_max_vector_delta_px']
integer_changes=[{'case':x['case'],'source':x['source'],'frame':x['frame'],'backend':b,'before':x['backend'][b]['before']['integer'],'after':x['backend'][b]['after']['integer']} for x in data for b in ['cpu','cuda'] if not x['backend'][b]['integer_unchanged']]
ratio_holds=maxafter<=pins['H_DC_max_allowed_px'];integer_holds=len(integer_changes)==0
runs=[json.loads(p.read_text()) for p in (root/'runs').glob('*/RUN.json')]
checks['exactly8-native-inverses-exit0']=len(runs)==8 and all(x['rc']==0 for x in runs)
checks['all8-frozen-inputs-unchanged']=all(x['all_frozen_files_unchanged'] for x in runs)
checks['all8-child-affinities']=all(x['child_affinities'] and all(t['mask']==list(range(80,88)) for t in x['child_affinities']) for x in runs)
checks['all4CUDA-fullbatch-projection-noop']=sum(x['backend']=='cuda' for x in runs)==4 and all(x['projection_noop'] and x['projected_bytes_identical'] and x['own_GPU2_witness'] for x in runs if x['backend']=='cuda')
checks['all8-fresh-admission']=all(json.loads(p.read_text())['admitted'] for p in (root/'runs').glob('*/ADMISSION.json'))
report={'frozen_plan_commit':'d10045e5cd4324eba62e189e5ffd256b42399557','pins_sha256':h.sha(P/'FROZEN-PINS.json'),'analysis_sha256':h.sha(__file__),'resource_helper_sha256':h.sha(h.__file__),'numerical_environment':envpin,'analytic_normalization_control':{'cosine_max_abs_error':analytic_diff,'cosine_bound':analytic_bound},'controls':checks,'all_controls_pass':all(checks.values()),'H_DC':{'status':'SUPPORTED' if ratio_holds and integer_holds else 'FALSIFIED','max_before_px':maxbefore,'max_after_px':maxafter,'after_before_ratio':ratio,'frozen_max_allowed_px':pins['H_DC_max_allowed_px'],'ratio_holds':ratio_holds,'integer_unchanged_all16_backend_input_pairs':integer_holds,'integer_changes':integer_changes,'is_acceptance_gate':False},'maps':data,'anchored_f4_minus_f0':anchored,'reference_output_files':outputs,'claim_boundary':'Producer-reported bounded operator arithmetic characterization, not native full-trajectory, motion-truth/science/parity acceptance or DC adoption. Historical DC/H7 harm and no-port evidence retained.'}
p=root/'ANALYSIS.json';assert not p.exists();p.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
print(json.dumps(report['H_DC'],indent=2));print('controls',sum(checks.values()),'/',len(checks),'all',report['all_controls_pass'])
for x in data:print(x['case'],x['source'],x['frame'],x['CPU_CUDA_before'],x['CPU_CUDA_after'])
