#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Frozen additive de-warp/re-estimate/refit experiment, with two image providers."""
import hashlib,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lib import *

verify();assert sys.argv[1:]==['--run-frozen-e2-dewarp']
def bilinear_source(image,p):
    x,y=p[...,0],p[...,1]
    ix,iy=np.floor(x).astype(int),np.floor(y).astype(int)
    valid=(ix>=0)&(iy>=0)&(ix+1<128)&(iy+1<96)
    cx,cy=np.clip(ix,0,127),np.clip(iy,0,95)
    out=image[cy,cx].astype(float)
    dx,dy=x[valid]-ix[valid],y[valid]-iy[valid];xx,yy=ix[valid],iy[valid]
    out[valid]=(1-dy)*((1-dx)*image[yy,xx]+dx*image[yy,xx+1])+dy*((1-dx)*image[yy+1,xx]+dx*image[yy+1,xx+1])
    return out.astype(np.float32),int((~valid).sum())

def warp(movie,recipe,fld,provider,sign):
    out=[];outside=[]
    for f in range(5):
        p=C.Q+sign*fld[f]
        if provider=='stored':
            img,n=bilinear_source(movie[f],p)
        else:
            img=C.generator.signal(recipe,C.generator.inverse(recipe,f,p)).astype(np.float32)
            n=int(((p[...,0]<0)|(p[...,1]<0)|(p[...,0]>=127)|(p[...,1]>=95)).sum())
        out.append(img);outside.append(n)
    return np.array(out),outside

movie,target,truth=C.fixture('affine');recipe=C.generator.recipe('affine')
native_g,native_c=C.state('affine')
true_g=truth[:,48,64];true_c,_=fit(np.array([truth[:,y,x]-true_g for x,y in C.CENTRES]),C.CENTRES)
assert np.abs(C.field(true_g,true_c)-truth).max()<1e-11
controls={};arms={}
# Source sampler controls use actual stored values, no fixture regeneration.
identity,_=warp(movie,recipe,np.zeros_like(truth),'stored',-1)
controls['stored_identity_exact']=bool(np.array_equal(identity,movie));assert controls['stored_identity_exact']
render,_=warp(movie,recipe,np.zeros_like(truth),'oracle',-1)
controls['oracle_identity_max_intensity_error']=float(np.abs(render.astype(float)-movie).max())
assert controls['oracle_identity_max_intensity_error']<1e-5

for provider in ('stored','oracle'):
    for mode in ('native-start','truth-trivial','wrong-sign','wrong-start-robustness','zero'):
        name=provider+'-'+mode
        if mode=='zero':
            mov,tgt,tr=C.fixture('zero');r=C.generator.recipe('zero');g=np.zeros((5,2));c=np.zeros((18,2))
        else:
            mov,tgt,tr,r=movie,target,truth,recipe
            if mode=='truth-trivial':g,c=true_g.copy(),true_c.copy()
            elif mode=='wrong-start-robustness':g,c=-native_g.copy(),-native_c.copy()
            else:g,c=native_g.copy(),native_c.copy()
        sign=1 if mode=='wrong-sign' else -1
        steps=[]
        for it in range(13):
            rr=field_result('e2-'+name+f'-{it:02d}',g,c,tr,mov,tgt,r)
            rr['iteration']=it
            if it<12:
                cur=C.field(g,c)
                warped,outside=warp(mov,r,cur,provider,sign)
                dg,dc,info=pipeline(warped,local=True,iters=5,tol=.5,gain=1.,map32=False)
                delta=C.field(dg,dc)
                rr.update(warp_sha256=sha(warped.tobytes()),outside_detector_pixels_per_frame=outside,
                    residual_update_roi_px=C.metrics(delta[:,12:84,12:116]),residual_estimation=info,
                    residual_global=dg.tolist(),residual_coefficients=None if dc is None else dc.tolist())
                g=g+dg
                if dc is not None:c=c+dc
            steps.append(rr)
        arms[name]=dict(provider=provider,mode=mode,warp_sign=sign,steps=steps)
        if mode=='truth-trivial':
            controls[provider+'_truth_trivial_first_update_near_zero']=steps[0]['residual_update_roi_px']['rms']<=1e-3
        elif mode=='wrong-sign':
            controls[provider+'_wrong_sign_never_passes']=all(not(s['runtime']['verdict']=='PASS' and s['STAR']['verdict']=='PASS') for s in steps)
        elif mode=='zero':
            controls[provider+'_zero_stays_zero']=max(s['runtime']['max'] for s in steps)<1e-11
        print(name,'initial',steps[0]['runtime'],'final',steps[-1]['runtime'],flush=True)
save('e2-dewarp.json',dict(kind='additive outer de-warp loop; stored primary and continuous-image oracle separately',
    controls=controls,arms=arms,near_zero_update_limit_px=1e-3,outer_iterations=12,
    native_source='805d9de27898b4a10e6212e65098d5995a40fdb1',
    native_CUDA_execution='UNRUN',negative_control='wrong-sign warp throughout; user clarified before execution'))
print('controls',controls,flush=True)
