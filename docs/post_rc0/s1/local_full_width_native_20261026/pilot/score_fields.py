"""Bounded field-only adapter around unchanged reviewed MotionCorr consumers.

This module launches nothing and reads no movie/reconstruction intensities.
Producer qualification requires complete_publication() first. field_metrics()
alone is deliberately a metadata-only calculation, not producer admission.
"""
from pathlib import Path
import hashlib,json,sys
import numpy as np

SOURCE=Path('/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6')
EXPECTED={
 'tools/check_motion_diagnostics.py':'2be34b821ce9c351abaeab5c0280478362cf90ba774df7f529caced9e360eb16',
 'tools/check_realistic_motion.py':'b0ab099a256e458b1c8aea6c2ff5d9ceacab10dd81945b025e96e5c8a87b7ff9',
 'tools/motion_field.py':'d72cfad7175368fa6d0727c2727c49780328951c6f4d3ecc20e9ac662ac2e810',
 'test-data/generate_motion_diagnostics.py':'5e781bb290b3f12b38f6dc7ec18bb955d56331219dc0216321e010ecbcdaf4cc',
 'test-data/generate_realistic_motion.py':'a10f694abafc71c146d0e0f2eeb2b1cf2c58131b2dbf6c1b66800405bd126380',
}
for name,h in EXPECTED.items():
 if hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=h:raise ValueError('consumer pin mismatch: '+name)
sys.path.insert(0,str(SOURCE/'tools'))
import check_motion_diagnostics as C
import check_realistic_motion as R
from motion_field import read_motion_star

LIMITS={'rms':.20,'p95':.40,'max':.80}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def complete_publication(run_dir,case,binary_sha256):
 """An exit0 or complete-looking tap alone never admits a row."""
 d=Path(run_dir);r=json.loads((d/'RUN.json').read_text())
 if r.get('exit')!=0 or r.get('binary_sha256')!=binary_sha256:raise ValueError('failed/unpinned producer')
 published=r.get('publication',{})
 required={case+'.star',case+'.mrc',case+'.log','corrected_micrographs.star','logfile.pdf'}
 if not required<=set(published):raise ValueError('incomplete publication receipt')
 for rel,pin in published.items():
  p=(d/'output'/rel).resolve()
  if not p.is_relative_to((d/'output').resolve()):raise ValueError('publication path escapes run')
  if not p.is_file() or p.stat().st_size!=pin['bytes'] or sha(p)!=pin['sha256']:raise ValueError('missing/changed publication: '+rel)
 if not (d/'runtime.json').is_file():raise ValueError('runtime tap missing')
 return r

def field_metrics(runtime_path,star_path,truth_path,case_meta,truth_sha256):
 r=case_meta['recipe'];roi=case_meta['roi'];shape=(r['frames'],r['ny'],r['nx'],2)
 if sha(truth_path)!=truth_sha256:raise ValueError('truth identity mismatch')
 truth=np.load(truth_path,allow_pickle=False)
 if truth.shape!=shape or not np.isfinite(truth).all():raise ValueError('truth geometry/nonfinite')
 model=json.loads(Path(runtime_path).read_text())
 if type(model.get('local_enabled')) is not bool:raise ValueError('invalid local_enabled')
 g=np.asarray(model.get('global'),dtype=float)
 cx=np.asarray(model.get('coeff_x'),dtype=float);cy=np.asarray(model.get('coeff_y'),dtype=float)
 if g.shape!=(r['frames'],2) or cx.shape!=(18,) or cy.shape!=(18,):raise ValueError('runtime geometry/coefficients')
 if not all(np.isfinite(a).all() for a in [g,cx,cy]):raise ValueError('nonfinite runtime')
 if not model['local_enabled'] and (cx.any() or cy.any()):raise ValueError('disabled model carries nonzero coefficients')
 C.validate_star_rows(Path(star_path),r)
 st=read_motion_star(star_path)
 if (st.nx,st.ny,st.n_frames,st.first_frame)!=(r['nx'],r['ny'],r['frames'],1):raise ValueError('STAR geometry')
 yy,xx=np.mgrid[:r['ny'],:r['nx']]
 rt=R.runtime_field(model,r,xx.ravel(),yy.ravel()).reshape(shape)
 sf=st.field(st.frames,xx.ravel(),yy.ravel()).reshape(shape)
 y0,y1,x0,x1=roi
 if not (0<=y0<y1<=r['ny'] and 0<=x0<x1<=r['nx']):raise ValueError('invalid fixed ROI')
 result={}
 for label,field in [('runtime',rt),('STAR',sf)]:
  if not np.isfinite(field).all():raise ValueError('nonfinite field')
  error=(field-truth)[:,y0:y1,x0:x1]
  aa=C.vector_metrics(error*r['pixel_size'])
  result[label]={'angstrom':aa,'px':C.vector_metrics(error),'gate':'PASS' if all(aa[k]<=LIMITS[k] for k in LIMITS) else 'FAIL'}
 result['local_enabled']=model['local_enabled']
 result['roundtrip_vector_max_px']=float(np.linalg.norm(rt-sf,axis=-1).max())
 result['scope']='FIELD_ONLY; publication/sampling/application/image/identifiability need separate checks'
 return result
