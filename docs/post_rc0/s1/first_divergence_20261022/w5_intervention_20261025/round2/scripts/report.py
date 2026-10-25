#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Saved-result tables/CSV only. No estimator, resampling or fixture execution."""
import csv
import hashlib
import json
import math
from pathlib import Path

R=Path(__file__).resolve().parents[1]
S=R/'results'
load=lambda n:json.loads((S/n).read_text())
ch,e1,e2=load('e1-characterization.json'),load('e1-intervention.json'),load('e2-dewarp.json')
old=json.loads((R.parent/'results/factorial.json').read_text())
def number(x):return f'{x:.3e}' if 0<abs(x)<1e-6 else f'{x:.6f}'
def triple(d):return ' / '.join(number(d[k]) for k in ('rms','p95','max'))
def tab(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows])
def same_roi_metrics(a):
    v=sorted(math.hypot(*x) for x in a); n=len(v); count=72*104
    pos=.95*(n*count-1); lo=math.floor(pos);hi=math.ceil(pos)
    q=v[lo//count]*(1-(pos-lo))+v[hi//count]*(pos-lo)
    return dict(rms=math.sqrt(sum(x*x for x in v)/n),p95=q,max=v[-1])
def star_g(name):
    lines=(S/'star'/(name+'.star')).read_text().split('data_global_shift')[1].split('data_')[0].splitlines()
    return [[float(t) for t in l.split()[1:]] for l in lines if len(l.split())==3 and l.split()[0].isdigit()]
stops=[]
for row in e1['stopping_terms']:
    iv,N,gain=row['velocity'],row['N'],row['gain']
    a=f'vel{iv}-N{N}-prod-gain{gain:g}-5it';b=f'vel{iv}-N{N}-prod-gain{gain:g}-50it'
    x,y=e1['probes'][a]['global_trajectory'],e1['probes'][b]['global_trajectory']
    sx,sy=star_g('e1-'+a),star_g('e1-'+b)
    diff=lambda u,v:[[(p[k]-q[k])*.885 for k in (0,1)] for p,q in zip(u,v)]
    stops.append(dict(velocity=iv,N=N,gain=gain,runtime_field_term_angstrom=same_roi_metrics(diff(x,y)),
        STAR_field_term_angstrom=same_roi_metrics(diff(sx,sy)),
        five_iteration_truth=row['five_iteration_truth'],fifty_iteration_truth=row['fifty_iteration_truth']))
derived=dict(kind='saved-endpoint field percentiles over repeated fixed ROI pixels; no estimator rerun',
    source_sha256=hashlib.sha256((S/'e1-intervention.json').read_bytes()).hexdigest(),rows=stops,
    note='e1-intervention.json also retains per-frame trajectory percentiles; these are full applied-field percentiles')
(S/'stopping-full-field.json').write_text(json.dumps(derived,indent=1)+'\n')

with (S/'e1-update-history.csv').open('w',newline='') as fp:
    w=csv.writer(fp,lineterminator='\n');w.writerow(['case','start_x_fraction','start_y_fraction','iteration','raw_update_rms_px','applied_update_rms_px','truth_error_rms_px'])
    for k,c in ch['cases'].items():
        for start,run in c['runs'].items():
            for row in run['history']:w.writerow([k,*start.split(','),*row])
with (S/'e2-iterations.csv').open('w',newline='') as fp:
    w=csv.writer(fp,lineterminator='\n');w.writerow(['arm','iteration','runtime_rms_A','runtime_p95_A','runtime_max_A','STAR_rms_A','STAR_p95_A','STAR_max_A','runtime_status','STAR_status','next_update_rms_px'])
    for k,a in e2['arms'].items():
        for s in a['steps']:w.writerow([k,s['iteration'],*[s[d][m] for d in ('runtime','STAR') for m in ('rms','p95','max')],s['runtime']['verdict'],s['STAR']['verdict'],s.get('residual_update_roi_px',{}).get('rms','')])

basin=[]
for k,c in ch['cases'].items():
    for start,s in c['runs'].items():
        basin.append([k,start,number(s['endpoint50_error_px']),number(s['endpoint500_error_px']),number(s['endpoint_update_rms_px']),s['classification']])
e1rows=[]
for case,c in e1['cases'].items():
    for arm,a in c['arms'].items():
        status='UNIDENTIFIABLE' if not c['identifiable'] else a['runtime']['verdict']+'/'+a['STAR']['verdict']
        e1rows.append([case,arm,triple(a['runtime']),triple(a['STAR']),status])
proberows=[[k,triple(a['runtime']),triple(a['STAR']),a['runtime']['verdict']+'/'+a['STAR']['verdict']] for k,a in e1['probes'].items()]
stoprows=[[s['velocity'],s['N'],s['gain'],triple(s['runtime_field_term_angstrom']),triple(s['STAR_field_term_angstrom']),number(s['five_iteration_truth']['rms']),number(s['fifty_iteration_truth']['rms'])] for s in stops]
e2rows=[]
for k in ('stored-native-start','oracle-native-start'):
    for s in e2['arms'][k]['steps']:
        e2rows.append([k,s['iteration'],triple(s['runtime']),triple(s['STAR']),s['runtime']['verdict']+'/'+s['STAR']['verdict']])
controlrows=[]
for k,a in e2['arms'].items():
    s=a['steps'][-1]
    controlrows.append([k,number(a['steps'][0]['residual_update_roi_px']['rms']),triple(s['runtime']),triple(s['STAR'])])

text='''# W5 Round 2: global dynamics and iterative de-warping

**E1 supports a bounded default-off CPU global half-gain prototype. E2 does
not qualify for a prototype: its stored-image truth-dewarp control fails.**
This is offline research on pinned original inputs, not native CPU/CUDA or
scientific qualification. No production source, default, gate, ROI or generator
changed. All new files are under this round2 directory.

## E1: the N5 endpoints are not wrong fixed points

The N5 phase-ramp 50-iteration errors are .391948/.392553 px, equivalent to
.346874/.347409 Å; the .347 number was Å. Four five-iteration baseline
trajectories reproduce the pinned W4/W5 double-map references **exactly**.
The unchanged peak rule reproduces all 65 captured float32 patch candidates
exactly. These checks establish offline arithmetic/reference fidelity;
NumPy float32-map replay is not a full native FFT/weight/shift reproduction.

After 500 forced updates from zero, fresh update RMS is .435449/.739949 px
for phase vel0/vel1 and .613469/.390646 px for retained integer/fractional.
Thus none is stationary. Last-state lag distances do not certify a cycle of
period1..8. Errors continue to fluctuate and are not a simple slowly shrinking
residual. Finite 500-step evidence cannot exclude a longer cycle, irregular
oscillation or much slower nonmonotone convergence; no mathematical chaos claim.
The strict period-two prediction was falsified.

Both ideal phase-ramp truth starts remain exactly at truth for 500 updates.
At truth the simultaneous anchored map has eigenvalues approximately .698524
and -1.192520, explaining why a nonzero perturbation is unstable. The 3x3
componentwise start grid finds no normal attraction basin to truth within
these sampled starts and500 updates. On the
stored fixtures the first update at true motion is only 1.63e-8/3.77e-7 px,
but it excites that instability: starting at truth also departs. This is
stationary truth in the ideal control, plus an unstable iteration, rather
than proof of an attractive wrong fixed point. Initialization alone is not
the selected repair.

[E1-PREDICTION.md](E1-PREDICTION.md) preceded characterization;
[E1-INTERVENTION-PREDICTION.md](E1-INTERVENTION-PREDICTION.md) preceded the one
candidate: scale the anchored GLOBAL update and its Fourier shift by .5,
while keeping the unscaled candidate RMS for stopping. Patch alignment is
unchanged. Local linearized eigenvalues become .849262 and -.096260.

The 50/1e-9 diagnostic meets all three limits for retained integer and
fractional in both double-map and float32-map replay, runtime AND STAR.
The float32-map results are .073975/.115201/.115201 Å for integer and
.104588/.163514/.163514 Å for fractional. The double-map results are much
smaller, but do not meet the 1e-9 update stop by iteration50; field PASS is
not numerical convergence. In map32 fractional50, the gain1 baseline already
passes at .081461 Å RMS, and gain.5 worsens it to .104588 Å while retaining
PASS. Thus that cell is not evidence of a gain-specific cure. With the
production5/.5 rule, map32 integer
passes (.181790/.244429/.244429 Å), while fractional still fails; double
fractional and affine pass, while double integer still fails. All results
remain on the original stored fixture samples, not on regenerated fixtures.

The full set and both stop rules were evaluated. No previously passing
retained identifiable case is lost within a matched arithmetic/stop domain.
There are important probe regressions: vel0 isotropic N13/N20 production-stop
controls change from PASS to FAIL. Gain.5 also increases several production-
weight five-stop errors at larger N. This is not a blanket recovery fix or a
proposal to change production stopping. Flat/repeated remain UNIDENTIFIABLE;
noisy remains characterization.

The mandatory harmful N20 vel1 isotropic case improves from 11.832823 to
**.391719229026 px RMS** at the five-stop rule; runtime
.346672/.517893/.631687 Å and STAR .346671/.517891/.631687 Å still FAIL.
At50/1e-9 it improves from11.827635 to5.26783e-10 px; both field representations
PASS. Both frozen harmful nonregression checks pass. This does not justify
adopting isotropic weights.

## E1 full fixture table

Scores are full applied fields, fixed material frame-zero gauge, all frames,
ROI y[12:84], x[12:116], .885 Å/px. Limits remain .20/.40/.80 Å. Runtime is
the float64 offline field; STAR is the field parsed from actual serialized
artifacts. Native baseline integer/fractional are .263614/.524057 Å RMS;
the new double/map32 baselines differ because these are declared offline
arithmetic domains. Do not subtract these numbers to claim a native gain.
map32 rounds the unnormalized CCF to float32 while retaining double Fourier
arithmetic. Source patch acceptance and null-model behavior remain active.

'''+tab(['Fixture','Arm','Runtime RMS / p95 / max Å','STAR RMS / p95 / max Å','Status'],e1rows)+'''

## E1 N controls, both stop rules and weights

Vel0=(-1,2), vel1=(-.8125,.53125) px/frame. These are the retained periodic
phase-ramp controls, not new gate-role image fixtures. Their global trajectories
define the entire applied field; some long trajectories put even truth outside
the finite detector ROI. Numeric field PASS is not an image/sampling PASS.
Every gain1 phase baseline matches W5 exactly, including the harmful row.

'''+tab(['Control / gain / stop','Runtime RMS / p95 / max Å','STAR RMS / p95 / max Å','Field status'],proberows)+'''

## Measured production stopping terms, N>=9

Ordered term = five-stop field minus fifty-stop field, not an independent
error contribution. The production gain1 terms are .237723–.437295 Å RMS;
every five-stop production control fails while its50-step field passes.
For example vel0 N9: field RMS .424674→.038813 Å, ordered term .437295 Å.
Cancellation explains why the term can exceed the initial error. Most
50-step cases still have converged=false at1e-9; “approaches truth” is the
supported claim. This is a candidate stopping-rule finding, not adoption.

Full-field percentiles below use every fixed-ROI pixel, including repetitions
within a frame. The original e1 JSON also retains per-frame trajectory
percentiles; [stopping-full-field.json](results/stopping-full-field.json) is
the additive saved-endpoint field calculation, with both endpoints rounded
through their actual STAR artifacts.

'''+tab(['Vel','N','Gain','Runtime term RMS / p95 / max Å','STAR term RMS / p95 / max Å','5-stop truth RMS Å','50-stop truth RMS Å'],stoprows)+'''

## E2: deformation can be reduced, but stored truth does not remain stationary

[E2-PREDICTION.md](E2-PREDICTION.md) fixes the algorithm, provider, edge rule,
12 outer iterations and controls before execution. Starting from the native
affine field, de-warp the original frames afresh, estimate residual global
and local motion with the inherited estimator, refit the same basis and add
the residual global+coefficients. E1 gain is not used. This is an additive
small-correction update, not exact composition of arbitrary warps.

The primary stored-image provider uses bilinear interpolation and the pinned
source's invalid-edge pixel fallback, with float32 image output. The separate
continuous-image oracle evaluates the exact original synthetic image function
at warped coordinates (including outside the finite detector). It is an image-
interpolation oracle using generator knowledge, not an adoptable estimator or
a replacement fixture. Its identity render matches stored samples exactly.

Stored-image native-start reaches the numeric contract at iteration2, loses
it at6/7, and ends at the frozen iteration12 at runtime
.173972/.327863/.408680 Å, STAR .173963/.327863/.408696 Å. The oracle provider
ends at .138888/.258565/.267886 Å, STAR .138873/.258542/.267859 Å. Neither
sequence demonstrates convergence to truth or monotonic progress; the best
intermediate iteration is not selected as an endpoint.

**The stored-image truth-dewarp control FAILS its frozen1e-3 px update check:**
first update .035504940254 px RMS. Starting at exact truth drifts to
.100219/.169024/.272041 Å by iteration12. The ideal-image truth control has
zero updates and stays at numerical zero; it is explicitly TRIVIAL, not
recovery. This demonstrates a finite-sample interpolation/boundary contribution
after true deformation is removed. The experiment does not split interpolation
from edge/window bias, and E1 instability, time/anchor convention, fit capacity
and additive composition remain co-causes of the outer loop's behavior.

The required wrong-sign warp throughout never passes and diverges to120.56 Å
RMS (stored) and344.46 Å (oracle). It is capable of failing. Both zero arms
stay exactly zero. The optional wrong-initial-estimate arms use normal warps;
they recover numerically and are separate basin/robustness evidence, not
negative controls. The stored wrong start first passes at iteration5 and
ends at .160147 Å RMS; the oracle wrong start ends at .132821 Å RMS.

Thus E2 has measured numerical passes, but does NOT satisfy its control-based
qualification for a prototype. The oracle cannot rescue the failed stored-
image control. No resampler, edge handling, generator, gauge or threshold was
retuned. All13 iterations for all10 arms, with runtime and STAR triples, are
in [e2-iterations.csv](results/e2-iterations.csv); the JSON also retains all
per-frame metrics, states, residual observations/acceptance and warp hashes.

'''+tab(['E2 arm','Iteration','Runtime RMS / p95 / max Å','STAR RMS / p95 / max Å','Field status'],e2rows)+'''

Control/robustness summary (full per-iteration records are linked above):

'''+tab(['Arm','First update RMS px','Iteration12 runtime RMS / p95 / max Å','Iteration12 STAR RMS / p95 / max Å'],controlrows)+'''

## Prototype recommendation and stop

**E1: worth one default-off CPU research prototype, scoped to global half-gain.**
At source805d9de2, add a default-off experimental option near parser line210;
in `MotioncorrRunner::alignPatch` after “Set origin” and accumulation of
unscaled x/y sumsq (around4824–4835), scale cur_x/y by.5 only when is_global
and that option is active, before BOTH accumulation into x/yshifts and the
Fourier re-shift. Keep the RMSD test on the unscaled sumsq. Do not damp local
patches, silently alter tolerance or enable the CUDA dispatch under this CPU
prototype. Native validation remains UNRUN and must test the recorded
five-stop regressions, not only a successful long-budget control.

Production tolerance is hard-coded .5 px. Existing --max_iter50 alone does
NOT reproduce the50/1e-9 diagnostic: it can still stop early. The strong long-
budget recovery therefore needs a separately explicit diagnostic tolerance
override in a test harness; it is not evidence for silently changing the
production stop. No stopping-rule or default change is recommended here.

**E2: no prototype recommendation**, despite its numerical passes. First
resolve the failed stored truth-dewarp control in a separately approved
experiment; do not fold E1 damping into this record or tune another resampler
now. The two mechanisms discriminate, so this task stops after E1 and E2.
No production implementation, native/GPU run, merge or scientific adoption.
CPU/CUDA agreement and current-head CI are UNRUN axes, not inferred passes.

## Reproduction and retained evidence

Parent cd4c996bdcffc0e7080aa8f817a11c5e449fe5c8; numerical source
805d9de27898b4a10e6212e65098d5995a40fdb1. INPUTS.json binds the accepted W5
manifest, source helpers, prior outputs and exact original W4 reference;
the parent W5 input manifest in turn binds every original fixture/capture.
All programs use Python -I and allow_pickle=False, validate hashes and refuse
output replacement. The three *FREEZE.json files bind each prediction and
executed scripts before that phase. Frozen scientific scripts are unchanged.
Reporting is saved-result processing, not another estimator experiment.

All three runs exited0 on cpu64 (small-refmac-machine), affinity48–55 under
nonblocking /tmp/motioncorr-w5-cpu48-55.lock, one BLAS/OpenMP thread,
NumPy2.5.3/Python3.12.3. Each launch receipt retains fresh one-second lane
occupancy. The assigned lane was idle or below the .5 admission ceiling;
an unrelated process on CPU57 was left alone. Remote owned scratch remains
under40 MB excluding the original transfer archives, and far below10 GB;
disk remained about94 GiB free. These timings/resources are not benchmarks.
VM originals and all previous W5/W4 records remain intact.

Commands, each run once:

```sh
R=/tmp/motioncorr-w5-20261025-7b76b848/round2
flock -n /tmp/motioncorr-w5-cpu48-55.lock taskset -c48-55 ~/.mc-venv/bin/python -I -B "$R/scripts/run_once.py" e1-characterization e1_characterize.py --run-frozen-e1-characterization
flock -n /tmp/motioncorr-w5-cpu48-55.lock taskset -c48-55 ~/.mc-venv/bin/python -I -B "$R/scripts/run_once.py" e1-intervention e1_intervention.py --run-frozen-e1-intervention
flock -n /tmp/motioncorr-w5-cpu48-55.lock taskset -c48-55 ~/.mc-venv/bin/python -I -B "$R/scripts/run_once.py" e2-dewarp e2_dewarp.py --run-frozen-e2-dewarp
```

The launcher path refers to the owned scratch retained from Round1; only its
new round2 subdirectory is written. To reproduce elsewhere, stage the parent
W5 hash-bound cache and helpers with this directory layout, choose a fresh
results namespace and obey the active resource allocation. No new fixture is
generated. [e1-update-history.csv](results/e1-update-history.csv) contains all
18,000 forced-update rows; the characterization JSON includes the3x3 basin
endpoints, lag distances, truth updates and full Jacobians. All294 generated
STAR files and complete coefficient/global states are retained. SHA256SUMS
binds the deliverable. The historical2 PASS/10 FAIL/4 UNIDENTIFIABLE ledger is
unchanged; these offline research results are additive.

### Full E1 basin endpoints

Each component start is its listed fraction of true motion. Endpoint fields
are scored separately in the JSON; this table is trajectory px for dynamics.

'''+tab(['Input','Start x,y','50-step error RMS px','500-step error RMS px','Endpoint update RMS px','Diagnostic label'],basin)+'\n'
(R/'README.md').write_text(text)

# A responsive saved-result table, suitable for the thread's inline artifact.
fixture_data=[]
for case,c in e1['cases'].items():
    if not c['identifiable']:continue
    for precision in ('double','map32'):
        for it in (5,50):
            b=c['arms'][f'{precision}-gain1-{it}it'];n=c['arms'][f'{precision}-gain0.5-{it}it']
            fixture_data.append(dict(case=case,precision=precision,it=it,baseline=triple(b['runtime']),runtime=triple(n['runtime']),star=triple(n['STAR']),status=n['runtime']['verdict']+'/'+n['STAR']['verdict']))
e2data={k:[dict(i=s['iteration'],runtime=triple(s['runtime']),star=triple(s['STAR']),status=s['runtime']['verdict']+'/'+s['STAR']['verdict']) for s in a['steps']] for k,a in e2['arms'].items()}
page='''<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;font:14px var(--font-sans,system-ui);color:var(--foreground,#222);line-height:1.5}p{margin:0 0 10px}select{font:inherit;color:inherit;background:var(--background,transparent);border:1px solid var(--border,#bbb);padding:5px;border-radius:6px;margin:0 8px 6px 0}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:12px}td,th{text-align:left;padding:8px 4px;border-bottom:1px solid var(--border,#ddd)}th{color:var(--muted-foreground,#666)}.note{font-size:12px;color:var(--muted-foreground,#666);margin-top:10px}.wrap{overflow-x:auto}</style></head><body>
<p><select id="which"><option value="e1">E1 global half-gain</option><option value="e2">E2 de-warp iterations</option></select><span id="e1pick"><select id="prec"><option>map32</option><option>double</option></select><select id="budget"><option value="50">50 / 1e-9</option><option value="5">5 / 0.5</option></select></span><select id="arm" hidden>'''
page+=''.join('<option>'+k+'</option>' for k in e2data)
page+='''</select></p><div class="wrap"><table><thead id="head"></thead><tbody id="body"></tbody></table></div><p class="note" id="note"></p><script>const fixtures='''+json.dumps(fixture_data)+''',iterations='''+json.dumps(e2data)+''';function draw(){let e1=which.value==='e1';document.getElementById('e1pick').hidden=!e1;arm.hidden=e1;if(e1){head.innerHTML='<tr><th>Fixture</th><th>Baseline runtime Å</th><th>Half-gain runtime Å</th><th>Half-gain STAR Å</th><th>Field gate</th></tr>';body.innerHTML=fixtures.filter(x=>x.precision===prec.value&&x.it===+budget.value).map(x=>`<tr><td>${x.case}</td><td>${x.baseline}</td><td>${x.runtime}</td><td>${x.star}</td><td>${x.status}</td></tr>`).join('');note.textContent='Triples: RMS / p95 / max Å. Offline replay; map32 uses double Fourier arithmetic. Limits 0.20 / 0.40 / 0.80 Å. No native qualification. Noisy is characterization.';}else{head.innerHTML='<tr><th>Iteration</th><th>Runtime RMS / p95 / max Å</th><th>STAR RMS / p95 / max Å</th><th>Field gate</th></tr>';body.innerHTML=iterations[arm.value].map(x=>`<tr><td>${x.i}</td><td>${x.runtime}</td><td>${x.star}</td><td>${x.status}</td></tr>`).join('');note.textContent='Stored truth-dewarp near-zero-update control FAILS (0.035505 px), despite numerical field passes. The oracle truth control is trivial. Both wrong-sign controls diverge; no E2 prototype qualification.';}}for(let id of ['which','prec','budget','arm'])document.getElementById(id).onchange=draw;draw();console.log('fixture records',fixtures.length,'E2 arms',Object.keys(iterations).length);</script></body></html>'''
(S/'report.html').write_text(page)
print('Rendered saved-result README, CSV, field stopping terms and HTML; no numerical rerun.')
