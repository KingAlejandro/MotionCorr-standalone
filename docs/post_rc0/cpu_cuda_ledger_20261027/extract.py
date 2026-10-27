#!/usr/bin/env python3
"""Extract recorded K269 comparisons and reconstruct Stage C runtime ROI fields.
Requires git access to the two pinned objects; no scientific job is run.
"""
import csv, io, json, math, subprocess, tarfile
from pathlib import Path
P=Path(__file__).resolve().parent
K='0a3099219827bebe8d410fd6f4b61d82350f0ce9:docs/post_rc0/s1/km_truth/backend_agreement.csv'
S='711c6edf9e8129b802fbd9cdae21f080f524251e:docs/post_rc0/ccf_dc_native_compat_20261026/evidence/stageC_run1/per_run_records.tar.gz'
def get(ref): return subprocess.check_output(['git','show',ref])
rows=[]
for r in csv.DictReader(io.StringIO(get(K).decode())):
    a=float(r['angstrom_rms']); c=r['condition']; arm=r['dc']
    note = ('measured pedestal sensitivity at condition level; row-specific cause unproved' if c=='pedestal32' else 'UNEXPLAINED: conditioning association only') if a>.02 else ''
    rows.append(['K269',f'{c}-s{int(r["seed"]):02}',arm,arm,r['px_rms'],r['angstrom_rms'], 'PASS' if a<=.02 else 'ABOVE',note])
tar=tarfile.open(fileobj=io.BytesIO(get(S)),mode='r:gz')
taps={}
for m in tar.getmembers():
    if m.name.endswith('/tap.json'):
        j=m.name.split('/')[-2]; taps[j]=json.load(tar.extractfile(m))
def find(case,backend,arm):
    z=[(k,v) for k,v in taps.items() if f'-K-{case}-{backend}-exp-{arm}-prod' in k]
    assert len(z)==1,(case,backend,arm,len(z)); return z[0]
def metric(a,b):
    total=0.; n=0
    for f in range(5):
        z=(f,f*f,f*f*f)
        for y in range(12,84):
            v=y/96-.5
            for x in range(12,116):
                u=x/128-.5; sp=(1,u,u*u,v,v*v,u*v); d=[]
                for axis,key in enumerate(('coeff_x','coeff_y')):
                    def value(t):
                        c=t[key]; return t['global'][f][axis]+sum(sum(c[3*g+i]*z[i] for i in range(3))*sp[g] for g in range(6))
                    d.append(value(a)-value(b))
                total+=sum(q*q for q in d); n+=1
    return math.sqrt(total/n)
for case in ('zero','affine','pedestal','noisy'):
    arms=('unset','none') if case=='zero' else ('none','global','local','both')
    for arm in arms:
        ja,a=find(case,'cpu',arm); jb,b=find(case,'cuda',arm); px=metric(a,b); ang=px*.885
        note='UNEXPLAINED: conditioning association; no case-specific causal trace' if ang>.02 else ''
        rows.append(['Stage C',case,arm,arm,format(px,'.15g'),format(ang,'.15g'),'PASS' if ang<=.02 else 'ABOVE',note+f' [{ja}; {jb}]'])
    if case!='zero':
        ja,a=find(case,'cpu','none'); jb,b=find(case,'cuda','both'); px=metric(a,b); ang=px*.885
        rows.append(['Stage C cross-arm',case,'none','both',format(px,'.15g'),format(ang,'.15g'),'PASS' if ang<=.02 else 'ABOVE','Different conditioning; causal contribution not isolated' + f' [{ja}; {jb}]'])
with (P/'field_pairs.csv').open('w',newline='') as f:
    w=csv.writer(f, lineterminator="\n"); w.writerow(['source','movie','cpu_arm','cuda_arm','rms_px','rms_angstrom','threshold','attribution']); w.writerows(rows)
from collections import Counter
print(Counter((r[0],r[2],r[3],r[6]) for r in rows))
