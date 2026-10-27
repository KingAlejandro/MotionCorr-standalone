"""Independent B64 fixed-total-G reproduction; no native-twin certification."""
from pathlib import Path
import ast,hashlib,json,struct
import numpy as np

ART=Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026')
SRC=Path('/tmp/mc-local-ccf-noise-twin-bridge-20261026')
B=ART/'Local-CCF-native-capture-r1/native-map-bundle-r1/evidence/runs/ON/capture'
truth=np.load(ART/'Local-CCF-native-capture-r1/capture-bundle-r1/truth-scoring-only/noisy_field.npy')
expected=json.loads((SRC/'RESULT_twin.json').read_text())
module=ast.parse((ART/'Local-CCF-parent-map-audit-r1/audit.py').read_text())
exec(compile(ast.Module(body=[x for x in module.body if isinstance(x,ast.FunctionDef) and x.name in ('basis','objective')],type_ignores=[]),'<parent-independent-trig>','exec'))

def read(p,tag):
 m=json.loads((p/(tag+'.json')).read_text())
 return np.fromfile(p/(tag+'.bin'),dtype=m['dtype']).reshape(m['shape'])

def movie(name,sha):
 raw=(SRC/'inputs'/f'{name}.mrcs').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==sha
 assert struct.unpack_from('<4i',raw)==(128,96,5,2)
 assert struct.unpack_from('<i',raw,92)[0]==0 and len(raw)==1024+5*96*128*4
 return np.frombuffer(raw,'<f4',offset=1024).reshape(5,96,128).astype(float)

movies={
 'noisy':movie('noisy','5000fbfc0d87cb4be7a8197685297176a2200f9c0d1866f94a7202aa5e85dab3'),
 'affine':movie('affine','1cf918d5da48d4c746020983017222829db9c949e362d07169a823bdc118260a')}
noise=np.random.Generator(np.random.PCG64(238262)).normal(0,4,(5,96,128))
rounding=(np.spacing(movies['noisy'].astype('f4')).astype(float)+np.spacing(movies['affine'].astype('f4')).astype(float))/2
residual=movies['noisy']-movies['affine']-noise
assert np.all(np.abs(residual)<=rounding)
rows=[]; max_error=0.
for cy,key in [(79,'patch_62_79_bad'),(47,'patch_62_47_central')]:
 p=B/f'patch-62-{cy}'
 g=read(p,'global-shifts')
 point=json.loads((p/'iter1-frame4-peak.json').read_text())['raw_scaled_xy_movie']
 f0=json.loads((p/'iter1-frame0-peak.json').read_text())['raw_scaled_xy_movie']
 scoring=truth[4,cy,62]-g[4]+f0
 w=read(p,'weights').astype(float)
 for name,raw in movies.items():
  transforms=[]; sample_error=0.
  for f in range(5):
   ft=np.fft.rfft2(raw[f],norm='forward')
   ky=np.arange(96); ky=np.where(ky>48,ky-96,ky)
   if f:
    ft*=np.exp(-2j*np.pi*(np.arange(65)[None,:]*g[f,0]/128+ky[:,None]*g[f,1]/96))
   shifted=np.fft.irfft2(ft,s=(96,128),norm='forward')
   y0=64 if cy==79 else 32
   sample=shifted[y0:y0+32,42:84]
   if name=='noisy': sample_error=max(sample_error,float(np.max(np.abs(sample-read(p,f'initial-frame{f}-samples')))))
   transforms.append(np.fft.rfft2(sample,norm='forward'))
  gaps=[]
  for j in range(4):
   s=transforms[j]*transforms[4].conj()*w; s[0,0]=0
   mp=np.fft.irfft2(s,s=(32,42),norm='forward')
   c=np.fft.fft2(mp)/(32*42)
   gap=objective(c,point)[0]-objective(c,scoring)[0]
   saved=expected['arms']['B64'][key][name]['components'][j]['gap_nat_minus_phys']
   error=abs(gap-saved); assert error<1e-9
   max_error=max(max_error,error);gaps.append(gap)
  rows.append({'patch':[62,cy],'input':name,'pairwise_gaps':gaps,'aggregate_pairwise_sum_gap':sum(gaps),'noisy_samples_native_max_abs_error':sample_error if name=='noisy' else None})
result={'scope':'B64 auxiliary bridge only; no native counterfactual bound, B32 audit, component peak audit or estimator change.',
 'max_gap_reproduction_error':max_error,'noise_rounding_residual_max':float(np.max(np.abs(residual))),
 'noise_rounding_bound_max':float(np.max(rounding)),'numpy':np.__version__,'rows':rows}
Path('VERIFIED.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
