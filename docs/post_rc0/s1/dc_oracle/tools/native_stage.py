#!/usr/bin/env python3
"""Validate the new native double path against independent full-complex maps.
Also trace the residual whole-movie R/Rprime difference into float input state.
"""
import json,pathlib,re,sys
import numpy as np
import stage
import analyze as a
s=pathlib.Path(sys.argv[1]);rows=[];feedback=[]
def index(d):return [l.split() for l in (d/'maps/index.txt').read_text().splitlines()]
def load(row,dt):return np.fromfile(row[0],dt).reshape(list(map(int,row[7:10])))
def product(frames,w,f):
 ref=np.zeros(frames.shape[1:],np.complex128)
 for z in frames:ref+=z.astype(np.complex128)
 z=frames[f].astype(np.complex128)
 return (ref-z)*z.conj()*w.astype(float)
for mv,g in [('e10216-00',3),('e12963-00',5)]:
 pair={}
 for arm in ['R','Rprime']:
  d=s/'runs'/f'{mv}-p{g}-capture-{arm}'
  if not (d/'run.json').exists():continue
  idx=index(d);recs=a.ccf(d);tag,iters=a.chosen(recs[(1,1)]);log=next((d/'Movies').glob('*.log')).read_text();m=re.search(r'Patch \(1, 1\): .*?X range = \[(\d+), (\d+)\), Y range = \[(\d+), (\d+)\)',log);x0,x1,y0,y1=map(int,m.groups());pnx,pny=x1-x0,y1-y0
  wt=load(next(r for r in idx if r[6]=='wt'),np.float32)[0]
  for inp in [r for r in idx if r[6]=='in']:
   k=int(inp[5]);fr=load(inp,np.complex64);n,ny,nfx=fr.shape;nx=2*(nfx-1);sx,sy=pnx/nx,pny/ny;r=int(50/max(sx,sy));r=min(r,nx//2-1,ny//2-1)
   pair[arm,k]=fr
   for f in range(n):
    z=product(fr,wt,f);base=z.copy();base[0,0]=0;refzero=stage.full_reference(base,nx);refnone=stage.full_reference(z,nx)
    native_row=next(q for q in idx if int(q[5])==k and q[6]=='map64fr'+str(f+1));native=load(native_row,np.float64)[0]
    ref=refnone if arm=='R' else refzero;sn=stage.select(native,r);sr=stage.select(ref,r);s0=stage.select(refzero,r);s1=stage.select(refnone,r)
    c=np.array([sx,sy]);q=iters[k][f+1]
    # Native five-sample capture remains float64 all the way to the text record.
    px,py=q['sel'];samples=[native[py%ny,px%nx],native[py%ny,(px+1)%nx],native[py%ny,(px-1)%nx],native[(py+1)%ny,px%nx],native[(py-1)%ny,px%nx]]
    rows.append({'config':f'{mv}-p{g}','arm':arm,'iteration':k,'frame':f+1,'native_map_vs_independent_max_error':float(np.max(abs(native-ref))),'native_candidate_vs_independent_px':float(np.linalg.norm((np.array(sn['candidate'])-sr['candidate'])*c)),'logged_candidate_vs_dump_px':float(np.linalg.norm(np.array(q['cur'])-np.array(sn['candidate'])*c)),'logged_samples_match_dump':q['sub']==samples,'fixed_input_double_DC_candidate_difference_px':float(np.linalg.norm((np.array(s0['candidate'])-s1['candidate'])*c)),'integer_match':sn['integer']==sr['integer']})
 for k in sorted(set(k for arm,k in pair if ('R',k) in pair and ('Rprime',k) in pair)):
  x,y=pair['R',k],pair['Rprime',k];v=(y.astype(np.complex128)-x);feedback.append({'config':f'{mv}-p{g}','iteration':k,'input_complex_coefficients_changed':int(np.count_nonzero(v)),'input_complex_coefficients':int(v.size),'input_max_abs_difference':float(np.max(abs(v))),'input_relative_l2_difference':float(np.linalg.norm(v.ravel())/np.linalg.norm(x.ravel()))})
res={'rows':rows,'feedback':feedback,'interpretation':'The native double CCF is checked on its own captured float inputs. R and Rprime can enter a local iteration with different float spectra after tiny global or previous-local shift differences. This is float state feedback, not a failure of fixed-input constant-offset invariance.'}
json.dump(res,open(s/'analysis/native-stage.json','w'),indent=1)
print('NATIVE FRAMES',len(rows),'map max',max(r['native_map_vs_independent_max_error'] for r in rows),'same input DC candidate max',max(r['fixed_input_double_DC_candidate_difference_px'] for r in rows),'native candidate max',max(r['native_candidate_vs_independent_px'] for r in rows));print('FEEDBACK',feedback)
assert all(r['logged_samples_match_dump'] and r['integer_match'] for r in rows)
assert max(r['logged_candidate_vs_dump_px'] for r in rows)<1e-10
