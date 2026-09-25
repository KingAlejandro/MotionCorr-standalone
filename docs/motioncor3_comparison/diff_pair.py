#!/usr/bin/env python3
"""Quantify the difference between two MRC images (magnitude, not a hash)."""
import sys, numpy as np
def rd(p):
    with open(p,"rb") as f:
        h=f.read(1024); nx,ny,nz,mode=np.frombuffer(h,dtype="<i4",count=4)
        ns=int(np.frombuffer(h,dtype="<i4",count=1,offset=92)[0])
        if ns: f.read(ns)
        d=np.fromfile(f,dtype={0:np.int8,1:np.int16,2:np.float32,6:np.uint16}[int(mode)],
                      count=int(nx)*int(ny)*max(int(nz),1))
    return d.reshape(int(ny),int(nx)).astype(np.float64)
a,b = rd(sys.argv[1]), rd(sys.argv[2])
d = a-b
nz = np.count_nonzero(d)
print(f"shape={a.shape} identical={nz==0}")
print(f"  n_differing_px = {nz} ({100.0*nz/d.size:.4f}%)")
print(f"  max_abs_diff   = {np.abs(d).max():.6g}")
print(f"  rmse           = {np.sqrt((d**2).mean()):.6g}")
print(f"  rel_rmse       = {np.sqrt((d**2).mean())/a.std():.6g}   (vs std {a.std():.6g})")
print(f"  a mean/std     = {a.mean():.6g} / {a.std():.6g}")
print(f"  b mean/std     = {b.mean():.6g} / {b.std():.6g}")
if nz:
    idx=np.unravel_index(np.argmax(np.abs(d)), d.shape)
    print(f"  worst px at y={idx[0]} x={idx[1]}: a={a[idx]:.6g} b={b[idx]:.6g}")
