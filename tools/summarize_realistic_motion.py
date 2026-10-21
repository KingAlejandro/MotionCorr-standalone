#!/usr/bin/env python3
"""Complete per-seed paired census; exact sign test, never pooled pixels."""
from __future__ import annotations
import argparse
import json
import gzip
import math
from pathlib import Path
import numpy as np
from check_realistic_motion import runtime_field, vector_metrics

ARMS=['cpu-none','cpu-global','cpu-local','cpu-both','cpu-double','cuda-none','cuda-global','cuda-local','cuda-both']
CONDITIONS=['dose1','dose05','dose2','dose4','outmodel','nonsquare','pedestal0','pedestal32','contrast025','contrast4']


def paired(a,b):
    """b-a: negative improves truth error. p is exact two-sided sign test."""
    a,b=np.asarray(a),np.asarray(b);d=b-a
    wins=int(np.sum(d < -1e-9));losses=int(np.sum(d > 1e-9));n=wins+losses
    p=min(1.,2*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/2**n) if n else 1.
    median=float(np.median(d))
    return dict(n=len(d),wins=wins,losses=losses,ties=len(d)-n,median_delta_px=median,
                min_delta_px=float(d.min()),max_delta_px=float(d.max()),
                median_ratio=float(np.median(b/a)) if np.all(a>0) else None,
                sign_test_two_sided_p=p,
                interpretation=('improves' if median<0 else 'harms') if p<.05 else 'neutral/mixed')


def summarize(root):
    rows=[];models={};receipts={};missing=[];full={}
    for c in CONDITIONS:
        for seed in range(10):
            name=f'{c}-s{seed:02d}'
            receipt=root/'fixtures'/name/'RECEIPT.json'
            if not receipt.exists():missing.append(str(receipt));continue
            receipts[name]=json.loads(receipt.read_text())
            for arm in ARMS:
                out=root/'results'/name/arm
                if not (out/'metrics.json').exists():missing.append(str(out/'metrics.json'));continue
                m=json.loads((out/'metrics.json').read_text());run=json.loads((out/'RUN.json').read_text());full[c,seed,arm]=m
                if run['exit']:raise ValueError('process failure cannot enter accuracy table')
                models[name,arm]=json.loads((out/'runtime.json').read_text())
                rows.append(dict(condition=c,seed=seed,arm=arm,field_px=m['field']['px'],field_angstrom=m['field']['angstrom'],
                    global_px=m['global_trajectory']['px'],local_px=m['local_component']['px'],
                    global_converged=m['convergence']['global_converged'],local_enabled=m['local_enabled'],
                    patches_converged=sum(p['converged'] for p in m['convergence']['patches']),
                    patches_total=len(m['convergence']['patches']),field_distance_status=m['field_distance_status'],
                    sampling_status=m['sampling_status'],star_roundtrip_loss_px=m['star_roundtrip_loss']['px']))
    if missing:raise ValueError(f'incomplete census: {len(missing)} missing; first: {missing[:5]}')
    index={(r['condition'],r['seed'],r['arm']):r for r in rows}
    table=[];comparisons=[];agreement=[];reference=[]
    for c in CONDITIONS:
        for arm in ARMS:
            rr=[index[c,s,arm] for s in range(10)]
            table.append(dict(condition=c,arm=arm,n=10,
                median_field_px={k:float(np.median([r['field_px'][k] for r in rr])) for k in ['rms','p95','max']},
                median_field_angstrom={k:float(np.median([r['field_angstrom'][k] for r in rr])) for k in ['rms','p95','max']},
                worst_field_max_px=max(r['field_px']['max'] for r in rr),
                median_global_rms_px=float(np.median([r['global_px']['rms'] for r in rr])),
                median_local_rms_px=float(np.median([r['local_px']['rms'] for r in rr])),
                global_nonconverged=sum(not r['global_converged'] for r in rr),
                local_disabled=sum(not r['local_enabled'] for r in rr),
                field_distance_failures=sum(r['field_distance_status']=='FAIL' for r in rr),
                invalid_sampling=sum(r['sampling_status']!='VALID' for r in rr)))
            baseline='cuda-none' if arm.startswith('cuda') else 'cpu-none'
            if arm!=baseline:
                metrics={}
                for family in ['field_px','global_px','local_px']:
                    metrics[family]=paired([index[c,s,baseline][family]['rms'] for s in range(10)],
                                           [index[c,s,arm][family]['rms'] for s in range(10)])
                comparisons.append(dict(condition=c,baseline=baseline,candidate=arm,metrics=metrics))
        for seed in range(10):
            name=f'{c}-s{seed:02d}';r=receipts[name]['recipe']
            x,y=np.meshgrid(np.linspace(32,r['nx']-33,129),np.linspace(32,r['ny']-33,129));x,y=x.ravel(),y.ravel()
            fields={a:runtime_field(models[name,a],r,x,y) for a in ARMS}
            for dc in ['none','global','local','both']:
                delta=fields['cuda-'+dc]-fields['cpu-'+dc]
                m=dict(px=vector_metrics(delta),angstrom=vector_metrics(delta*r['pixel_size']))
                agreement.append(dict(condition=c,seed=seed,dc=dc,field_distance=m))
            for arm in ARMS:
                if arm=='cpu-double':continue
                delta=fields[arm]-fields['cpu-double']
                m=dict(px=vector_metrics(delta),angstrom=vector_metrics(delta*r['pixel_size']))
                reference.append(dict(condition=c,seed=seed,arm=arm,field_distance=m,
                                      within_descriptive_001px=m['px']['max']<=.001))
    temporal=[]
    for c in CONDITIONS:
        for arm in ARMS:
            for frame in range(receipts[f'{c}-s00']['recipe']['frames']):
                row=dict(condition=c,arm=arm,frame=frame+1)
                for family in ['field','global_trajectory','local_component']:
                    row[family+'_median_px']={k:float(np.median([full[c,seed,arm][family]['per_frame_px'][frame][k] for seed in range(10)])) for k in ['rms','p95','max']}
                temporal.append(row)
    return dict(schema='motion-counting-summary/1',rows=rows,table=table,paired=comparisons,temporal=temporal,
                backend_agreement=agreement,double_reference_distance=reference,
                statistics='Exact two-sided sign tests of paired per-seed RMS; |delta|<=1e-9 px ties; exploratory multiplicity',
                limitations=['Fixed 129x129 spatial lattice, not pooled detector pixels','Noise seeds share one generated scene',
                             'Double CCF from float frame spectra, not a double movie pipeline','No residual frequency transfer or downstream science'])


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--json',type=Path,required=True)
    args=ap.parse_args();data=json.dumps(summarize(args.root),indent=2,allow_nan=False)+'\n'
    if args.json.suffix=='.gz': args.json.write_bytes(gzip.compress(data.encode(),mtime=0))
    else: args.json.write_text(data)

if __name__=='__main__':main()
