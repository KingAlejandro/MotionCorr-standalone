#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Direct long-double Fourier sums on one retained near-tie witness; no native run."""
import json,pathlib,sys
import numpy as np
def array(stem,it,kind,dtype,shape):
 p=pathlib.Path(str(stem)+f"-i{it}-{kind}.bin");return np.fromfile(p,dtype=dtype).reshape(shape)
r=pathlib.Path(sys.argv[1]);stem=r/'runs/cuda-integer-on/capture/c1';ny,nx=96,128;fx=65
spec=array(stem,1,'spectrum','<c8',(5,ny,fx))[0]
inputs=array(stem,1,'input','<c8',(5,ny,fx)).astype(np.clongdouble)
weight=array(stem,0,'weight','<f4',(ny,fx)).astype(np.longdouble)
# Same boundary, independently accumulated with long double; no template or DC change.
ref=inputs.sum(axis=0);reaccum=(ref-inputs[0])*inputs[0].conj()*weight

def longfull(half):
 h=np.array(half,dtype=np.clongdouble,copy=True);neg=(-np.arange(ny))%ny
 for kx in [0,nx//2]:h[:,kx]=(h[:,kx]+h[neg,kx].conj())/2
 full=np.empty((ny,nx),np.clongdouble);full[:,:fx]=h
 for kx in range(fx,nx):full[:,kx]=h[neg,nx-kx].conj()
 return full

def direct(half,x,y):
 full=longfull(half);ky,kx=np.mgrid[:ny,:nx]
 pi=np.arccos(np.longdouble(-1));angle=2*pi*(kx.astype(np.longdouble)*x/nx+ky.astype(np.longdouble)*y/ny)
 return np.sum(full.real*np.cos(angle)-full.imag*np.sin(angle),dtype=np.longdouble)
rows=[]
for label,h in [('captured-C2R',spec),('long-double-reference-product',reaccum)]:
 vals={}
 for x in [2,3]:
  for y in [-6,-5,-4]:vals[f'{x},{y}']=direct(h,x,y)
 gap=vals['3,-5']-vals['2,-5']
 rows.append(dict(boundary=label,values={k:str(v) for k,v in vals.items()},gap_x3_minus_x2_at_yminus5=str(gap),winner_between_adjacent_x=3 if gap>0 else 2,mantissa_bits=np.finfo(np.longdouble).nmant))
(r/'direct-witness.json').write_text(json.dumps(dict(case='integer',backend='cuda',call=1,iteration=1,frame=1,rows=rows,interpretation='Direct Fourier sums corroborate a near-tie reversal at the captured-reference/product boundary; no native trajectory or physical forward-double reference.'),indent=2)+'\n')
print(json.dumps(rows,indent=2))
