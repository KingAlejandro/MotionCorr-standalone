#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Frozen E1 endpoint and basin characterization; no estimator intervention yet."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lib import *

verify()
assert sys.argv[1:]==['--run-frozen-e1-characterization']
old=json.loads((W5/'results/factorial.json').read_text())
ind=json.loads((R/'inputs/indep.json').read_text())
_,target,_=C.fixture('integer'); E=Estimator(); Ft=np.fft.fft2(target.astype(float))/(128*96)
cases={}
for j,v in enumerate(((-1.,2.),(-.8125,.53125))):
    t=np.arange(5)[:,None]*np.array(v)
    F=np.array([E.shift(Ft,-a) for a in t]);cases['phase-vel'+str(j)]=(F,t)
for k in ('integer','fractional'):
    movie,_,truth=C.fixture(k); cases['fixture-'+k]=(np.fft.fft2(movie.astype(float))/(128*96),truth[:,0,0])
results={}; checks={}
for name,(F,t) in cases.items():
    e=Estimator()
    reference=e.run(F,5,.5,truth=t)
    if name.startswith('phase'):
        j=name[-1]; ref=np.array(old['probes'][f'vel{j}-N5-prod-5it']['global_trajectory'])
    else: ref=np.array(ind[name[8:]]['sumothers_parabola_5it']['traj'])
    gap=float(np.abs(reference['state']-ref).max());checks[name+'_reproduction_max_px']=gap
    assert gap<1e-5
    runs={}
    for ax in (0.,.5,1.):
        for ay in (0.,.5,1.):
            start=t*np.array([ax,ay])
            rr=e.run(F,500,1e-9,start=start,force=True,truth=t,keep_states=True)
            s=rr.pop('states'); endpoint=rr['state']
            lag={str(p):rms(s[-1]-s[-1-p]) for p in range(1,9)}
            u=rr['endpoint_update_rms_px']
            if u<1e-7: verdict='FIXED_POINT'
            elif min(lag.values())<1e-6:
                verdict='LIMIT_CYCLE_PERIOD_'+next(str(p) for p in range(1,9) if lag[str(p)]<1e-6)
            elif rr['history'][-1][1]<rr['history'][49][1]*.5: verdict='SLOW_OR_IRREGULAR_CONVERGENCE'
            else: verdict='NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED'
            runs[f'{ax:g},{ay:g}']=dict(**serial(rr),lag_rms_px=lag,classification=verdict,
                endpoint50=s[50].tolist(),endpoint50_error_px=rms(s[50]-t),
                endpoint500_error_px=rms(endpoint-t),
                tail_states=s[-9:].tolist(),
                score=field_result(name+f'-start{ax:g}_{ay:g}',endpoint,None,np.broadcast_to(t[:,None,None],(5,96,128,2))))
    # Numerically differentiate the simultaneous anchored iteration at truth.
    def M(s):
        fs=np.array([e.shift(f,x) for f,x in zip(F,s)])
        return s+e.update(fs)
    eps=1e-3; J=np.zeros((8,8))
    for i in range(8):
        d=np.zeros_like(t);d[1+i//2,i%2]=eps
        J[:,i]=((M(t+d)-M(t-d))/(2*eps))[1:].ravel()
    ev=np.linalg.eigvals(J)
    results[name]=dict(truth=t.tolist(),truth_one_step_update_px=(M(t)-t).tolist(),truth_one_step_rms_px=rms(M(t)-t),
         jacobian_step_px=eps,jacobian=J.tolist(),eigenvalues=[[float(x.real),float(x.imag)] for x in ev],
         spectral_radius=float(np.abs(ev).max()),runs=runs)
    print(name,[(k,v['classification'],v['endpoint500_error_px'],v['endpoint_update_rms_px']) for k,v in runs.items()],flush=True)
save('e1-characterization.json',dict(kind='E1 baseline endpoint/basin calculation, 500 forced iterations, same inherited parabolic map',
    checks=checks,cases=results,history_columns=['iteration','raw_update_rms_px','applied_update_rms_px','truth_error_rms_px'],
    diagnostic_limits=dict(fixed_point_update_px=1e-7,small_period_lag_px=1e-6)))
