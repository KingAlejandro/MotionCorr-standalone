from pathlib import Path
import json, hashlib, ast
import numpy as np

ROOT=Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026')
bundle=ROOT/'Local-CCF-native-capture-r1/native-map-bundle-r1'
truth=np.load(ROOT/'Local-CCF-native-capture-r1/capture-bundle-r1/truth-scoring-only/noisy_field.npy')
original=Path('/tmp/mc-local-ccf-pairwise-ref-20261026')
result=json.loads((original/'RESULT.json').read_text())
# Reuse only the direct Fourier-series evaluation from the already independent
# parent audit, without importing/rerunning its other computations.
module=ast.parse((ROOT/'Local-CCF-parent-map-audit-r1/audit.py').read_text())
functions=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in ('basis','objective')]
exec(compile(ast.Module(body=functions,type_ignores=[]),'<parent-independent-trig>','exec'))
def read(p,t):
 m=json.loads((p/(t+'.json')).read_text())
 return np.fromfile(p/(t+'.bin'),dtype=m['dtype']).reshape(m['shape'])
def spectrum(p,t):
 a=read(p,t).astype(float)
 return a[...,0]+1j*a[...,1]
rows=[]
for cy,key in [(79,'patch_62_79_bad'),(47,'patch_62_47_central')]:
 p=bundle/f'evidence/runs/ON/capture/patch-62-{cy}'
 g=read(p,'global-shifts')
 raw=json.loads((p/'iter1-frame4-peak.json').read_text())['raw_scaled_xy_movie']
 f0=json.loads((p/'iter1-frame0-peak.json').read_text())['raw_scaled_xy_movie']
 physical=truth[4,cy,62]-g[4]+f0
 f4=spectrum(p,'iter1-frame4-window-fft'); w=read(p,'weights').astype(float)
 gaps=[]; maps=[]
 for j in range(4):
  sj=spectrum(p,f'iter1-frame{j}-window-fft')*f4.conj()*w
  sj[0,0]=0
  mp=np.fft.irfft2(sj,s=(32,42),norm='forward')
  c=np.fft.fft2(mp)/(32*42)
  gap=objective(c,raw)[0]-objective(c,physical)[0]
  saved=result['patches'][key]['pairwise_components_j0_to_3'][j]['fixed_point_evaluations']['gap_nat_minus_phys']
  assert abs(gap-saved)<1e-14
  gaps.append(gap); maps.append(mp)
 native=read(p,'iter1-frame4-real-map').astype(float)
 summed=np.sum(maps,axis=0)
 native_c=np.fft.fft2(native)/native.size
 native_gap=objective(native_c,raw)[0]-objective(native_c,physical)[0]
 rows.append({'patch':[62,cy],'pairwise_gaps':gaps,'sum_gap':sum(gaps),'native_gap':native_gap,'native_minus_sum_gap':native_gap-sum(gaps),'auxiliary_map_native_max_abs_error':float(np.max(np.abs(summed-native))),'actual_global_shifts':g.tolist()})
out={'rows':rows,'max_scalar_reproduction_error_tolerance':1e-14,'numpy':np.__version__,'scope':'Eight fixed-point objective gaps only; not component peak search, causal interpretation, native execution or a new estimator.'}
Path('VERIFIED.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
