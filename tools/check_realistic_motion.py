#!/usr/bin/env python3
"""Truth metrics on a fixed 129x129 spatial lattice; no per-frame registration."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'test-data'))
import generate_realistic_motion as gen
from check_motion_diagnostics import validate_star_rows, vector_metrics
from motion_field import read_motion_star


def runtime_field(model, r, x, y):
    u,v=x/r['nx']-.5,y/r['ny']-.5
    spatial=np.stack([np.ones_like(u),u,u*u,v,v*v,u*v])
    z=np.arange(r['frames'],dtype=float)
    temporal=np.stack([z,z*z,z*z*z])
    coeff=np.array([model['coeff_x'],model['coeff_y']]).reshape(2,6,3)
    return np.einsum('agt,tf,gp->fpa',coeff,temporal,spatial)+np.asarray(model['global'])[:,None,:]


def errors(field,truth,pixel_size):
    e=field-truth
    return dict(px=vector_metrics(e),angstrom=vector_metrics(e*pixel_size),
                per_frame_px=[vector_metrics(a) for a in e],
                per_frame_angstrom=[vector_metrics(a*pixel_size) for a in e])


def evaluate(r, model, serialized=None):
    # Fixed lattice declared before runs, including a separate full-border lattice.
    x,y=np.meshgrid(np.linspace(32,r['nx']-33,129),np.linspace(32,r['ny']-33,129))
    x,y=x.ravel(),y.ravel()
    truth=-np.stack([gen.displacement(r,f,x,y) for f in range(r['frames'])])
    field=runtime_field(model,r,x,y)
    if not np.isfinite(field).all(): raise ValueError('nonfinite runtime field')
    g=-np.stack([gen.displacement(r,f,np.array([r['nx']/2]),np.array([r['ny']/2]))[0] for f in range(r['frames'])])
    # The analytic local field is nonzero at the center: use its declared constant drift.
    if not r['control']:
        t=np.arange(r['frames'])/(r['frames']-1)
        g=-np.stack([8*(-np.expm1(-t/.1))+4*t,-5*(-np.expm1(-t/.15))-2*t],axis=-1)
    result=dict(schema='motion-counting-metrics/1',gauge='frame-0 material; no registration',
                lattice=dict(shape=[129,129],roi=[32,r['ny']-33,32,r['nx']-33],endpoints_inclusive=True),
                field=errors(field,truth,r['pixel_size']),global_trajectory=errors(np.array(model['global']),g,r['pixel_size']),
                local_component=errors(field-np.array(model['global'])[:,None,:],truth-g[:,None,:],r['pixel_size']),
                local_enabled=model['local_enabled'],signal_transfer_status='UNRUN: no frequency-transfer adapter',
                role='characterization',sampling_status='VALID')
    aa=result['field']['angstrom']
    result['field_distance_status']='PASS' if aa['rms']<=.20 and aa['p95']<=.40 and aa['max']<=.80 else 'FAIL'
    source=np.stack((x,y),axis=-1)[None,:,:]-field
    if (source[...,0].min()<0 or source[...,1].min()<0 or source[...,0].max()>=r['nx']-1 or source[...,1].max()>=r['ny']-1):
        result['sampling_status']='OUTSIDE_FIXED_ROI'
    bx=np.r_[np.linspace(0,r['nx']-1,129),np.linspace(0,r['nx']-1,129),np.zeros(129),np.full(129,r['nx']-1)]
    by=np.r_[np.zeros(129),np.full(129,r['ny']-1),np.linspace(0,r['ny']-1,129),np.linspace(0,r['ny']-1,129)]
    bt=-np.stack([gen.displacement(r,f,bx,by) for f in range(r['frames'])])
    result['border']=errors(runtime_field(model,r,bx,by),bt,r['pixel_size'])
    if serialized is not None:
        sf=serialized.field(serialized.frames,x,y)
        result['serialized_field']=errors(sf,truth,r['pixel_size'])
        result['star_roundtrip_loss']=errors(sf,field,r['pixel_size'])
    return result


def convergence(log):
    text=Path(log).read_text()
    global_text=text.split('Global alignment:',1)[1].split('Local alignments:',1)[0]
    it=[float(a) for a in re.findall(r'Iteration \d+: RMSD = (\S+) px',global_text)]
    patches=[]
    for block in re.split(r'Patch \(\d+, \d+\):',text)[1:]:
        vals=[float(a) for a in re.findall(r'Iteration \d+: RMSD = (\S+) px',block)]
        patches.append(dict(final_increment_px=vals[-1] if vals else None,converged=bool(vals and vals[-1]<.5)))
    return dict(global_iterations=len(it),global_increment_px=it,global_converged=bool(it and it[-1]<.5),patches=patches)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--receipt',type=Path,required=True); ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--star',type=Path,required=True); ap.add_argument('--log',type=Path,required=True)
    ap.add_argument('--json',type=Path,required=True); args=ap.parse_args()
    receipt=json.loads(args.receipt.read_text()); r=receipt['recipe']
    if receipt['schema']!=gen.SCHEMA: raise ValueError('unsupported receipt')
    validate_star_rows(args.star,r); serialized=read_motion_star(args.star)
    model=json.loads(args.runtime.read_text())
    if np.asarray(model['global']).shape!=(r['frames'],2): raise ValueError('runtime geometry mismatch')
    result=evaluate(r,model,serialized); result['convergence']=convergence(args.log)
    result['identity']={str(p):gen.digest(p) for p in [args.receipt,args.runtime,args.star,args.log]}
    args.json.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')

if __name__=='__main__': main()
