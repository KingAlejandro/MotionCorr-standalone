#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Default-off offline unit-group observation convention experiment; no native run.

Run python -I intervention.py --run-frozen-convention-experiment. All upstream
native trajectories, patch acceptance and measured observations stay fixed.
"""
import io
import json
from pathlib import Path
import re
import sys
import tarfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *

assert sys.argv[1:] == ['--run-frozen-convention-experiment'], 'default off: explicit frozen experiment switch required'
verify()
assert sha((ROOT/'EXTRA-INPUTS.json').read_bytes())=='6ec3b6127be33176c915949b62dcd7fa3308eb7c640a1319c2ae70da03313c67'
extra = json.loads((ROOT/'EXTRA-INPUTS.json').read_text())
for rel, pin in extra.items():
    b=(IN/'extra'/rel).read_bytes()
    assert len(b)==pin['bytes'] and sha(b)==pin['sha256']
assert extra['native-receipts.tar.gz']['sha256']=='def6ab01874e4ff5a118feb3e307f80e6bdcee5973358cd3b0484526b3ec2435'
ARM = {'A00': (.5, True), 'A10': (0., True), 'A01': (.5, False), 'A11': (0., False)}
OUT = ROOT/'results/star'
OUT.mkdir(exist_ok=False)

def fit_arm(local, coords, arm):
    offset, extrap = ARM[arm]
    n, nf, _ = local.shape
    xy = np.array(coords,float)
    z=np.broadcast_to(np.arange(nf,dtype=float)+offset,(n,nf))
    A=basis(np.broadcast_to(xy[:,0:1]/NX-.5,(n,nf)),np.broadcast_to(xy[:,1:2]/NY-.5,(n,nf)),z).reshape(-1,18)
    obs=local-(1.5*local[:,:1]-.5*local[:,1:2]) if extrap else local-local[:,:1]
    c,res,rank,sv=np.linalg.lstsq(A,obs.reshape(-1,2),rcond=None)
    assert rank==18 and np.isfinite(c).all()
    return c,dict(rank=int(rank), condition=float(sv[0]/sv[-1]), residual_sum_squares=res.tolist())

def fmt(v):
    # metadata_table.cpp:254-278 at 805d9de2 (C buffer width 12).
    exp=(0<abs(v)<.001) or abs(v)>100000
    return format(float(v), ('.5' if v<0 else '.6')+('e' if exp else 'f'))

def rounded(a):
    return np.array([float(fmt(v)) for v in a.ravel()]).reshape(a.shape)

def write_star(label,g,c):
    s=['data_general',f'_rlnImageSizeX {NX}',f'_rlnImageSizeY {NY}',f'_rlnImageSizeZ {len(g)}',
       '_rlnMicrographStartFrame 1', '_rlnMicrographBinning 1.000000',
       '_rlnMicrographOriginalPixelSize .885000',f'_rlnMotionModelVersion {int(c is not None)}',
       '', 'data_global_shift', 'loop_', '_rlnMicrographFrameNumber #1',
       '_rlnMicrographShiftX #2','_rlnMicrographShiftY #3']
    s += [f'{f+1} {fmt(row[0])} {fmt(row[1])}' for f,row in enumerate(g)]
    if c is not None:
        s += ['', 'data_local_motion_model','loop_','_rlnMotionModelCoeffsIdx #1','_rlnMotionModelCoeff #2']
        s += [f'{i} {fmt(v)}' for i,v in enumerate(c.T.ravel())]
    p=OUT/(label+'.star'); p.write_text('\n'.join(s)+'\n')
    st=read_motion_star(p)
    sf=st.field(st.frames,Q[...,0].ravel(),Q[...,1].ravel()).reshape(len(g),NY,NX,2)
    assert np.abs(sf-field(rounded(g),None if c is None else rounded(c))).max()<1e-10
    return sf,sha(p.read_bytes())

def one(label,g,c,truth,movie=None,target=None,recipe=None):
    ff=field(g,c)
    sf,starhash=write_star(label,g,c)
    out=dict(runtime=score(ff,truth), STAR=score(sf,truth),
             runtime_minus_STAR_max_px=float(np.abs(ff-sf).max()),
             global_trajectory=g.tolist(), coefficients=None if c is None else c.tolist(),
             star_sha256=starhash, centre_trajectory=ff[:,48,64].tolist(),
             per_frame_runtime_angstrom=[metrics(e*PIX) for e in (ff-truth)[:,12:84,12:116]],
             per_frame_STAR_angstrom=[metrics(e*PIX) for e in (sf-truth)[:,12:84,12:116]])
    if movie is not None:
        out['application']={}
        for name,f in [('runtime',ff),('STAR',sf)]:
            ev=checker.evaluate(recipe,movie,target,truth,f,ROI)
            assert max(abs(ev['field_angstrom'][k]-out[name][k]) for k in ('rms','p95','max'))<1e-12
            out['application'][name]=dict(sampling=ev['sampling_status'],signal=ev['signal'])
    else:
        lo=(Q[12:84,12:116][None]-truth[:,12:84,12:116]).min((0,1,2))
        hi=(Q[12:84,12:116][None]-truth[:,12:84,12:116]).max((0,1,2))
        out['application']=dict(kind='periodic phase-ramp control; constant applied field',
            truth_detector_sampling='OUTSIDE_FIXED_ROI' if (lo<0).any() or hi[0]>=127 or hi[1]>=95 else 'VALID',
            signal='UNRUN_NOT_A_NEW_IMAGE_FIXTURE')
    return out

archive=tarfile.open(IN/'extra/native-receipts.tar.gz')
idx=json.loads((IN/'extra/native-index.json').read_text())['files']
def native_star(case):
    rel=f'cases-cpu/{case}/{case}.star'
    b=archive.extractfile(rel).read(); assert sha(b)==idx[rel]['sha256']
    p=OUT/('retained-'+case+'.star'); p.write_bytes(b)
    return read_motion_star(p)

controls={}
cases={}
for case in ('zero','integer','fractional','affine','pedestal','noisy'):
    movie,target,truth=fixture(case)
    st=native_star(case)
    if case in ('integer','fractional','affine','noisy'):
        g,nc=state(case)
        # Roundtrip formatter must reproduce every retained native scalar exactly.
        controls[case+'_native_STAR_global_roundtrip']=bool(np.array_equal(rounded(g),np.stack((st.global_shift_x,st.global_shift_y),axis=-1)))
        if nc is not None:
            controls[case+'_native_STAR_coeff_roundtrip']=bool(np.array_equal(rounded(nc),np.stack((st.coeff_x,st.coeff_y),axis=-1)))
    else:
        g=np.stack((st.global_shift_x,st.global_shift_y),axis=-1)
        nc=None if st.motion_model_version==0 else np.stack((st.coeff_x,st.coeff_y),axis=-1)
        assert not g.any() and (nc is None or not nc.any())
    coords=[]; local=None
    provenance='captured full-precision global; no local fit'
    if case=='affine':
        local=captured_local(); coords=CENTRES
        provenance='captured full-precision global AND all 45 local observations'
    elif case in ('pedestal','noisy'):
        by={}
        for row in st.local_shifts:
            xy=(int(row['rlnCoordinateX']),int(row['rlnCoordinateY']))
            by.setdefault(xy,{})[int(row['rlnMicrographFrameNumber'])-1]=[row['rlnMicrographShiftX'],row['rlnMicrographShiftY']]
        coords=list(by)
        local=np.array([[by[xy][f] for f in range(5)] for xy in coords])
        local-=local[:,:1]
        if case=='pedestal':
            assert not local.any()
            provenance='zero reconstruction from retained STAR/logs; full-precision native capture unavailable'
        else:
            provenance='STAR-rounded observation sensitivity ONLY; native full-precision local observations unavailable'
    elif case=='zero':
        provenance='zero reconstruction from retained STAR/logs; full-precision native capture unavailable'
    rec=dict(provenance=provenance, arms={}, native_runtime=None if case in ('zero','pedestal') else score(field(g,nc),truth),
             native_STAR=score(st.field(st.frames,Q[...,0].ravel(),Q[...,1].ravel()).reshape(5,NY,NX,2),truth),
             local_observations=None if local is None else local.tolist(),local_coordinates=coords)
    baseline=None
    for arm in ARM:
        cc,info=fit_arm(local,coords,arm) if local is not None else (None,{})
        if case=='affine' and arm=='A00':
            gap=float(np.abs(field(g,cc)-field(g,nc)).max()); controls['native_affine_fit_closure']=gap<1e-11
            rec['native_baseline_closure_max_px']=gap
        rr=one(case+'-'+arm,g,cc,truth,movie,target,generator.recipe(case)); rr['fit']=info
        rec['arms'][arm]=rr
        if baseline is None: baseline=field(g,cc)
        rr['field_change_from_A00_max_px']=float(np.abs(field(g,cc)-baseline).max())
    if case in ('zero','integer','fractional','pedestal'):
        controls[case+'_no_change']=all(v['field_change_from_A00_max_px']==0 for v in rec['arms'].values())
    cases[case]=rec

# Ideal known observation controls, same fit and application, no capacity-floor subtraction.
_,_,truth=fixture('affine'); g,_=state()
ideal={}
for name,gg in [('actual_global',g),('true_global',truth[:,48,64])]:
    ll=np.array([truth[:,y,x]-gg for x,y in CENTRES])
    ideal[name]={}
    for arm in ARM:
        c,info=fit_arm(ll,CENTRES,arm)
        ideal[name][arm]=one('ideal-'+name+'-'+arm,gg,c,truth)
        ideal[name][arm]['fit']=info
    if name=='true_global':
        for arm in ('A00','A11'):
            controls['linear_cancel_'+arm]=ideal[name][arm]['runtime']['max']<1e-11*PIX
        for arm in ('A10','A01'):
            controls['linear_mutant_'+arm]=ideal[name][arm]['runtime']['rms']>.01

# Pinned independent review's full-complex replay definitions, no main block.
src=(IN/'retained/review/round1/indep.py').read_text().split('out = {}')[0]
oldargv=sys.argv; sys.argv=['indep.py',str(IN)]
ns={}; exec(compile(src,'pinned-indep.py[definitions]','exec'),ns); sys.argv=oldargv
tgt=np.load(IN/'fixtures/integer_target.npy',allow_pickle=False).astype(float)
Ft=np.fft.fft2(tgt)/(128*96)
log=(IN/'retained/review/round1/ndep.log').read_text().splitlines()
probes={}
max_repro=0.
for iv,vel in enumerate(((-1.,2.),(-.8125,.53125))):
    for j,N in enumerate((5,9,13,20)):
        tt=np.arange(N)[:,None]*np.array(vel)[None]
        truth=np.broadcast_to(tt[:,None,None],(N,NY,NX,2))
        F0=np.stack([ns['shiftF'](Ft,-t) for t in tt]); ns['NF']=N
        expected=[float(v) for v in re.findall(r'rms=([0-9.]+)',log[iv*4+j])]
        k=0
        for wn,W in [('prod',ns['W_prod']),('iso',ns['W_iso'])]:
            for it,tol in [(5,.5),(50,1e-9)]:
                acc,conv,hist=ns['replay'](F0,W,iters=it,tol=tol)
                err=rms(acc-tt); delta=abs(err-expected[k]); k+=1
                max_repro=max(max_repro,delta); assert delta<=.000501
                key=f'vel{iv}-N{N}-{wn}-{it}it'
                rr=one(key,acc,None,truth)
                rr.update(converged=bool(conv), rmsd_history=hist, trajectory_error_px=metrics(acc-tt),
                          retained_rounded_rms_px=expected[k-1], reproduction_difference_px=delta,
                          arm_ids=list(ARM), arm_field_change_max_px={a:0. for a in ARM},
                          interpretation='no local fit: intervention structurally inapplicable; all arms share this exact trajectory')
                probes[key]=rr
controls['all_ndep_reproduction']=max_repro<=.000501
harm=probes['vel1-N20-iso-5it']
controls['harmful_counterexample_retained']=abs(harm['trajectory_error_px']['rms']-11.833)<=.000501
controls['harmful_counterexample_no_regression']=all(v==0 for v in harm['arm_field_change_max_px'].values())
assert all(controls.values()), controls
out=dict(kind='W5 observation convention factorial; offline, default off; CPU/CUDA agreement UNRUN',
         arms={a:dict(time_offset=v[0],zero_time_extrapolation=v[1]) for a,v in ARM.items()},
         controls=controls,cases=cases,ideal_controls=ideal,probes=probes,
         max_ndep_rounded_reproduction_error_px=max_repro,
         recommendation='FALSIFIED: no default-off C++ prototype recommendation unless a previously failing identifiable fixture passes runtime AND STAR',
         extra_input_manifest_sha256=sha((ROOT/'EXTRA-INPUTS.json').read_bytes()),
         prediction_sha256=sha((ROOT/'PREDICTION.md').read_bytes()))
save('factorial.json',out)
print(json.dumps(dict(controls=controls,
    cases={k:{a:dict(runtime=v['runtime'],STAR=v['STAR']) for a,v in c['arms'].items()} for k,c in cases.items()},
    harmful=dict(runtime=harm['runtime'],STAR=harm['STAR'],trajectory_error_px=harm['trajectory_error_px'])),indent=1))
