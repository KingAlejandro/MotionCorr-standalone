#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Frozen E1 half-gain GLOBAL update; unchanged local estimator."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lib import *

verify();assert sys.argv[1:]==['--run-frozen-e1-intervention']
old=json.loads((W5/'results/factorial.json').read_text())
checks={};worst=0.
for iy in range(1,4):
    for ix in range(1,4):
        p=C.IN/f'matched/captures/patch-{iy}-{ix}'
        e=Estimator(42,32)
        for cp in p.glob('c2-i*-candidate.bin'):
            it=cp.name.split('-')[1]
            candidate=np.frombuffer(cp.read_bytes(),'<f8').reshape(5,2)
            for f in range(5):
                m=np.frombuffer((p/f'c2-{it}-map-f{f}.bin').read_bytes(),'<f4').reshape(32,42)
                worst=max(worst,float(np.abs(e.peak(m)-candidate[f]).max()))
checks['stored_float32_peak_replay_max_px']=worst;assert worst<=1e-6

cases={}
for case in ('zero','integer','fractional','affine','pedestal','noisy','flat','repeated'):
    movie,target,truth=C.fixture(case); recipe=C.generator.recipe(case)
    local=case in ('affine','pedestal','noisy')
    rec=dict(role=recipe['role'],identifiable=recipe['signal'] not in ('flat','repeated'),arms={})
    for map32 in (False,True):
        precision='map32' if map32 else 'double'
        for gain in (1.,.5):
            for it,tol in ((5,.5),(50,1e-9)):
                key=f'{precision}-gain{gain:g}-{it}it'
                e=Estimator(map32=map32);F=np.fft.fft2(movie.astype(float))/(128*96)
                gr=e.run(F,it,tol,gain=gain);g=gr['state']
                cc=None;localinfo={}
                if local:
                    aligned=np.array([np.fft.ifft2(e.shift(F[f],g[f])).real*(128*96) for f in range(5)])
                    # The ONLY changed factor is global gain; local gain remains 1.
                    cc,localinfo=patch_fit(aligned,it,tol,gain=1.,map32=map32)
                rr=field_result('e1-'+case+'-'+key,g,cc,truth,movie,target,recipe)
                rr.update(global_run=serial(gr),local=localinfo,
                    acceptance=rr['runtime']['verdict'] if rec['identifiable'] else 'UNIDENTIFIABLE')
                rec['arms'][key]=rr
    cases[case]=rec
    print(case,{a:v['runtime'] for a,v in rec['arms'].items()},flush=True)

E=Estimator();_,target,_=C.fixture('integer');Ft=np.fft.fft2(target.astype(float))/(128*96)
probes={};repro=0.
for iv,vel in enumerate(((-1.,2.),(-.8125,.53125))):
    for N in (5,9,13,20):
        t=np.arange(N)[:,None]*np.array(vel);F=np.array([E.shift(Ft,-x) for x in t])
        truth=np.broadcast_to(t[:,None,None],(N,96,128,2))
        for weight in ('prod','iso'):
            for gain in (1.,.5):
                for it,tol in ((5,.5),(50,1e-9)):
                    key=f'vel{iv}-N{N}-{weight}-gain{gain:g}-{it}it'
                    rr=Estimator(weight=weight).run(F,it,tol,gain=gain,truth=t)
                    if gain==1:
                        ref=np.array(old['probes'][f'vel{iv}-N{N}-{weight}-{it}it']['global_trajectory'])
                        gap=float(np.abs(ref-rr['state']).max());repro=max(repro,gap);assert gap<1e-5
                    out=field_result('e1-'+key,rr['state'],None,truth)
                    out.update(run=serial(rr),trajectory_error_px=C.metrics(rr['state']-t))
                    probes[key]=out
checks['phase_baseline_reproduction_max_px']=repro
stopping=[]
for iv in (0,1):
    for N in (9,13,20):
        for gain in (1.,.5):
            a=probes[f'vel{iv}-N{N}-prod-gain{gain:g}-5it']
            b=probes[f'vel{iv}-N{N}-prod-gain{gain:g}-50it']
            x=np.array(a['global_trajectory']);y=np.array(b['global_trajectory'])
            # Serialization affects each endpoint independently.
            def rnd(v):
                return np.array([float(format(z,'.5f' if z<0 else '.6f')) for z in v.ravel()]).reshape(v.shape)
            stopping.append(dict(velocity=iv,N=N,gain=gain,
                runtime_term_angstrom=C.metrics((x-y)*PIX),STAR_term_angstrom=C.metrics((rnd(x)-rnd(y))*PIX),
                five_iteration_truth=a['runtime'],fifty_iteration_truth=b['runtime'],
                five_iterations_used=a['run']['iterations'],fifty_iterations_used=b['run']['iterations']))
harm={}
for it in (5,50):
    base=probes[f'vel1-N20-iso-gain1-{it}it'];new=probes[f'vel1-N20-iso-gain0.5-{it}it']
    harm[str(it)]=dict(baseline_rms_px=base['trajectory_error_px']['rms'],candidate_rms_px=new['trajectory_error_px']['rms'],
        nonregression=new['trajectory_error_px']['rms']<=base['trajectory_error_px']['rms']+1e-6,
        runtime=new['runtime'],STAR=new['STAR'])
save('e1-intervention.json',dict(kind='global half-gain only, offline NumPy, native/CUDA agreement UNRUN',
    controls=checks,cases=cases,probes=probes,stopping_terms=stopping,harmful_counterexample=harm))
print('harmful',harm,flush=True)
