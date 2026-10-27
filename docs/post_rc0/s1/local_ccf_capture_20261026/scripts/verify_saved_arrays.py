"""Complete frozen stage-accounting checks on retained arrays only; no fit/producer."""
import importlib.util,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
import numpy as np
ROOT=Path('/tmp/motioncorr-local-ccf-20261026');OUT=ROOT/'array-verification-v1'
spec=importlib.util.spec_from_file_location('saved',ROOT/'analyze_capture.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def native_shift(a,delta):
 nfy,nfx=a.shape[:2];ky=np.arange(nfy);ky=np.where(ky>nfy//2,ky-nfy,ky)
 px=2*np.pi*np.arange(nfx)*(-delta[0]/42);py=2*np.pi*ky*(-delta[1]/32)
 sx,cx=np.sin(px),np.cos(px);sy,cy=np.sin(py),np.cos(py)
 b=sx[None,:]*cy[:,None]+cx[None,:]*sy[:,None];aa=cx[None,:]*cy[:,None]-sx[None,:]*sy[:,None]
 c,d=a[...,0].astype('f8'),a[...,1].astype('f8');ac=aa*c;bd=b*d;abcd=(aa+b)*(c+d)
 return np.stack([ac-bd,abcd-ac-bd],axis=-1).astype('f4')
OUT.mkdir(exist_ok=False);rows=[]
for cy in (47,79):
 d=m.CAP/f'patch-62-{cy}';w=m.array(d,'weights');weights=np.empty_like(w)
 for y in range(32):
  ly=y-32 if y>16 else y
  for x in range(22):weights[y,x]=np.exp(-2*(ly*float(ly)/(32*float(32))+x*float(x)/(22.*22.))*150)
 rows.append(dict(patch=[62,cy],stage='weights scalar-double expression castfloat32',max_error=m.maxerr(w,weights),exact=np.array_equal(w,weights)))
 for it in (1,2):
  ref=m.array(d,f'iter{it}-reference');deltas=m.array(d,f'iter{it}-applied-deltas')
  for f in range(5):
   tag=f'iter{it}-frame{f}';ff=m.array(d,tag+'-enter-fft');window=m.array(d,tag+'-window-fft');assert np.array_equal(ff,window)
   if it==1:assert np.array_equal(ff,m.array(d,f'initial-frame{f}-fft'))
   else:assert np.array_equal(ff,m.array(d,f'iter{it-1}-frame{f}-exit-fft'))
   other=ref-window;real=other[...,0]*window[...,0]-other[...,1]*(-window[...,1]);imag=other[...,0]*(-window[...,1])+other[...,1]*window[...,0];raw=np.stack([real,imag],axis=-1)
   pre=np.stack([w*real,w*imag],axis=-1);actual=m.array(d,tag+'-weighted-pre-dc')
   # Scalar float operations mirror tComplex, rather than a NumPy complex multiplication kernel.
   assert np.array_equal(raw,m.array(d,tag+'-raw-product'))
   assert np.array_equal(pre,actual)
   exit_=m.array(d,tag+'-exit-fft');expected=ff if f==0 else native_shift(ff,deltas[f])
   rows.append(dict(patch=[62,cy],iteration=it,frame=f,raw_and_weighted_scalar_float_expression_exact=True,full_window_fft_exact=True,postshift_max_component_error=m.maxerr(expected,exit_),postshift_exact=np.array_equal(expected,exit_)))
m.write(OUT/'RESULT.json',dict(scope='retained array verification only; all stages from frozen analysis protocol; no numerical gate change',rows=rows))
print('PASS scalar float raw+weighted expression exact all20; max shift component error',max(r.get('postshift_max_component_error',0) for r in rows))
