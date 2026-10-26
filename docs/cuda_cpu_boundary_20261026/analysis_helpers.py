#!/usr/bin/env python3
"""Read-only comparisons, finite checks and hashes; never modifies products."""
import argparse,hashlib,json,pathlib,struct,sys
import numpy as np
R=pathlib.Path('/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026')
sys.path.insert(0,'/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src/tools')
from motion_field import read_motion_star

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(a,b):
 assert a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all()
 d=b.astype(np.float64)-a.astype(np.float64)
 return {'count':int(a.size),'different_bits':int(np.count_nonzero(a.view(np.uint32)!=b.view(np.uint32))),'rmse':float(np.sqrt(np.mean(d*d))),'max_abs':float(np.max(np.abs(d)))}
def payload(p):
 with open(p,'rb') as f:h=f.read(1024)
 nx,ny,nz,mode=struct.unpack_from('<4i',h);assert mode==2
 ext=struct.unpack_from('<i',h,92)[0];a=np.memmap(p,dtype='<f4',mode='r',offset=1024+ext,shape=(nz,ny,nx));assert p.stat().st_size==1024+ext+a.size*4
 return a
def products(phase,label,case):
 d=R/phase/label/'out/Movies';s=f'20170629_{case}_frameImage'
 return d/(s+'.mrc'),d/(s+'.star')
def compare_products(pa,pb):
 ma,sa=pa;mb,sb=pb;a=payload(ma);b=payload(mb);o=stats(a,b);o['relative_rmse']=o['rmse']/max(float(np.std(a,dtype=np.float64)),1e-12)
 aa=read_motion_star(sa);bb=read_motion_star(sb);o['star_text_equal']=sa.read_bytes()==sb.read_bytes()
 o['global_vector_rms_px']=float(np.sqrt(np.mean((aa.global_shift_x-bb.global_shift_x)**2+(aa.global_shift_y-bb.global_shift_y)**2)))
 x,y=np.meshgrid(np.linspace(.1*aa.nx,.9*aa.nx,17),np.linspace(.1*aa.ny,.9*aa.ny,17));d=bb.field(aa.frames,x.ravel(),y.ravel())-aa.field(aa.frames,x.ravel(),y.ravel())
 o['STAR_field_vector_rms_px_17x17_10to90pct']=float(np.sqrt(np.mean(np.sum(d*d,axis=-1))))
 o['local_observation_counts']=[len(aa.local_shifts),len(bb.local_shifts)]
 o['hashes']={str(p):sha(p) for p in [ma,sa,mb,sb]}
 return o
def geometry(d):return {k:float(v) for k,v in (l.split() for l in (d/'geometry.txt').read_text().splitlines())}
def peak(m,g):
 r=int(g['search_range']);xs=np.arange(-r,r+1);yy,xx=np.meshgrid(xs,xs,indexing='ij');vals=m[yy%m.shape[0],xx%m.shape[1]];mx=vals.max();ties=np.argwhere(vals==mx);j,i=ties[0];y,x=int(xs[j]),int(xs[i]);c=float(m[y%m.shape[0],x%m.shape[1]])
 def delta(vp,vn):
  den=float(vp)+float(vn)-2*c
  return -.5*(float(vp)-float(vn))/den if abs(den)>1e-15 else 0
 px=(x+delta(m[y%m.shape[0],(x+1)%m.shape[1]],m[y%m.shape[0],(x-1)%m.shape[1]]))*g['nx']/g['ccf_nx']
 py=(y+delta(m[(y+1)%m.shape[0],x%m.shape[1]],m[(y-1)%m.shape[0],x%m.shape[1]]))*g['ny']/g['ccf_ny']
 return {'integer':[x,y],'ties':len(ties),'shift_px':[px,py],'max':float(mx)}
def hermitian(s):
 vals=[]
 for x in [0,s.shape[1]-1]:
  a=s[:,x];b=np.conj(a[(-np.arange(len(a)))%len(a)]);vals.append(float(np.max(np.abs(a-b))))
 return {'column_max_conjugacy_error':vals,'valid':all(v==0 for v in vals)}
