#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Render saved measurements only. No numerical rerun or acceptance changes."""
import html
import json
from pathlib import Path

R=Path(__file__).resolve().parents[1]
f=json.loads((R/'results/factorial.json').read_text())
c=json.loads((R/'results/challenge.json').read_text())
def triple(x): return ' / '.join(f'{x[k]:.6f}' for k in ('rms','p95','max'))
def table(rows):
    return '\n'.join(['| Case | Arm | Runtime RMS / p95 / max Å | STAR RMS / p95 / max Å | Verdict |',
        '|---|---|---|---|---|']+['| '+' | '.join(row)+' |' for row in rows])
rows=[]
for case,rec in f['cases'].items():
    for a,v in rec['arms'].items():
        rows.append([case+(' *' if case in ('noisy','zero','pedestal') else ''),a,triple(v['runtime']),triple(v['STAR']),v['runtime']['verdict']+'/'+v['STAR']['verdict']])
ideal=[]
for case,rec in f['ideal_controls'].items():
    for a,v in rec.items(): ideal.append([case,a,triple(v['runtime']),triple(v['STAR']),v['runtime']['verdict']+'/'+v['STAR']['verdict']])
probes=[]
for case,v in f['probes'].items(): probes.append([case,'A00=A10=A01=A11',triple(v['runtime']),triple(v['STAR']),v['runtime']['verdict']+'/'+v['STAR']['verdict']])
text='''# W5 motion-truth challenge and one offline intervention

**Verdict: objective bias is demonstrated on the same captured native inputs.
The convention intervention is falsified as a recovery fix. No default-off C++
prototype is recommended from this experiment.**

## Challenge to W4

On all nine CPU patch spectra, frame i correlated against the **truth-aligned
sum of others** gives 0.343210025860 px anchored trajectory error RMS (frames
1–4). The equivalent update at truth is 0.343210025860 px. Every frame/patch
has positive AC-objective gain on moving away from truth (minimum 1.45e-7 in
the unnormalized spectral objective). Pure-translation phase-ramp controls give
exactly zero update. Absolute-reference and shifted-coordinate calculations
agree within 5.24e-11 px. This establishes (a): the inherited weighted finite
window CCF already prefers motion away from centre truth. It rules out (b) as
the sole explanation here. No global-maximum certification is claimed.

The zero-start continuous fixed point reproduces W4 within 7.78e-16 px and remains
0.274906500584 px from truth. Restarting at truth returns within 3.21e-6 px of
that endpoint. The small endpoint difference is retained, not called exact
equality. W4's R_fm is a static frame-zero template; R_loo and R_pipe_loo start
at zero and iterate to their own fixed point. None was the oracle reference
above. Their common MIXED label did **not** establish truth stationarity.

(c) is also a co-cause, not an exclusive alternative to (a). With ideal known
centre observations and the actual nonlinear global trajectory, the inherited
convention yields 0.214314 Å RMS; the paired integer-time/frame-zero convention
yields 0.085462 Å. With true linear global motion, both conventions reproduce
the field at numerical precision. Unit groups contain one instantaneous
synthetic frame; there is no exposure-time integration to explain these errors.
The source's half-frame fit time and extrapolated zero anchor cancel for linear
motion; changing one alone breaks that exact property.

The spatial residual is more than half-pixel centre rounding. An additive
geometry calculation on the saved oracle result finds that 35/36 nonzero-frame
observations would need an effective coordinate outside their patch to equal a
single nonnegative scalar content-weighted average of this affine material
field; 25/36 exceed at least one component's whole-patch range. This excludes
that simple convex-average explanation. Tensor/signed gradient weighting,
hard-window/periodic boundary effects and material/Eulerian sampling mismatch
remain entangled. A physical effective coordinate has not been measured.

W4's fit closure, ordered path decomposition, substantial peak/float32 terms,
and statement that peak arithmetic alone cannot cure truth error survive. The
45-observation fit again closes to the native field within 1.96e-14 px (rank 18,
condition 4069.25; residual sums .755968x/.604868y). This repeat was the required
baseline validation, not a new fit qualification. The path RMS terms remain
non-additive scalar summaries. Interpreting the .275 px residual as an iteration
problem with stationary truth fails this test; interpreting it as a proven
simple spatial average also fails. W4's corrected convention counterfactuals
remain counterfactuals, never unconditional capacity floors.

## Frozen intervention and result

[PREDICTION.md](PREDICTION.md) was frozen before Part 2; [FREEZE.json](FREEZE.json)
binds it, the Part-1 output and the executed scripts. One intervention, two
single-factor arms and their single interaction:

- A00: inherited z=f+.5, O=L+.5L[1].
- A10: integer time z=f, same inherited observations.
- A01: inherited time, frame-zero observations O=L.
- A11: paired integer time and frame-zero observations.

L is the fixed captured local trajectory anchored to frame zero. No field is
registered after fitting. Every arm keeps global estimates, accepted patches,
centres, weight, peak estimator, stop rule, fit basis and application fixed.
The offline program is default off and requires an explicit experiment switch.
No production source changed. The source locations for this rejected candidate
are the unit-group observation collection near motioncorr_runner.cpp:3815–3833
at 805d9de2, not the peak or polynomial solver.

Prediction confirmed: A11 improves the ideal-observation control but does not
recover the actual affine fixture. Its actual runtime RMS drops 0.085308 Å
(21.2%) to .317130 Å; p95 .651866 Å still fails. No previously failing fixture
passes all .20/.40/.80 Å RMS/p95/max limits in both representations. The zero
control remains the only passing retained identifiable fixture. A11 also
worsens the noisy STAR-observation sensitivity RMS by 1.138161 Å; this is
additional counter-evidence, with its input-precision limitation retained.

## Per-case factorial

Runtime means the full float64 **offline reconstructed applied field**, global
plus the 18-term local model, at every frame and pixel in fixed ROI y[12:84],
x[12:116], .885 Å/px. STAR means the field parsed from the generated serialized
STAR, using the pinned asymmetric 5/6-decimal formatting. These are separate
scores, not native execution or image-publication witnesses. Source evaluator
metrics agree within 1e-12 Å. No tolerance, ROI, fixture, mask or scoring changed;
no model-capacity floor was subtracted.

* Zero/pedestal use the retained all-zero STAR/log state; full-precision native
captures do not exist for these two. Their float64 zero reconstruction is not
presented as a newly captured native runtime. Noisy uses rounded STAR local
observations and is sensitivity-only; its true captured-native baseline is
2.342955/4.376571/9.903899 Å, and the A00 refit differs slightly. Affine uses all
45 captured full-precision local observations. Integer/fractional use captured
full-precision native globals and have no local model; this intervention is a
structural no-op there.

'''+table(rows)+'''

The historical 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE ledger is unchanged. This
CPU experiment does not regrade CUDA. Flat/repeated remain UNIDENTIFIABLE and
are not converted into acceptance cases.

## Ideal observations through the identical fit

These use known centre observations only as diagnostic controls, never as
estimator recovery. Single-factor arms lose exact linear cancellation even
where the loose motion-truth limits still pass.

'''+table(ideal)+'''

## N controls and harmful counterexample

Vel0=(-1,2), vel1=(-.8125,.53125) px/frame. All four convention arms are
identical for each control because these periodic phase-ramp trajectories
have no local fit. The table explicitly applies to **each** A00/A10/A01/A11.
These structural no-op controls do not qualify local fitting at longer frame
counts or with multi-frame groups; those paths remain UNRUN.
Both the five-iteration/.5 px rule and the 50-iteration/1e-9 diagnostic are
retained. All 32 inherited RMS values reproduce ndep.log to its .001 px
printed precision. The isotropic rows are retained harmful comparator controls,
not a weight intervention or adoption proposal.

The mandatory N20 fractional isotropic five-iteration case remains
**11.832822522791 px RMS**, runtime 10.472048/14.810680/14.811067 Å,
STAR 10.472049/14.810683/14.811072 Å. Intervention difference is exactly zero.
It remains harmful; nonregression is not recovery. Its 50-iteration error also
remains retained. Numeric PASS below describes only the diagnostic field
distance: these synthetic phase ramps are not new gate-role image fixtures;
long trajectories can put even truth outside the detector's unchanged ROI.
Sampling flags are retained in factorial.json; signal is UNRUN for the probes.

'''+table(probes)+'''

## Recommendation and limits

**Falsified as a recovery intervention.** The favorable ideal-observation
prediction does not survive actual observations, and the noisy sensitivity
arm worsens. Stop after this one factorial; no C++ prototype, production
default/gate change, merge or estimator adoption follows.

Next discriminating experiment: on the same captured windows and frozen truth,
compare the measured oracle-reference displacement with the translation
obtained from a spatial gradient-tensor observation model evaluated over the
known affine deformation. Use an exact periodic-translation control and a
truth-warped/common-support control to separate spatial content weighting
from finite-window boundary bias **before** proposing a weight change. Do not
assign a fitted effective centre outside the physical patch or tune it on
these results. This next experiment is UNRUN.

CPU/CUDA agreement is a separate UNRUN axis. Existing backend differences and
all historical failures remain. No native MotionCorr, GPU/CUDA, performance
or new scientific qualification was run. The applied-image numbers here are
offline evaluator bilinear characterizations, not native resampling witnesses.

## Reproducibility and receipts

Pinned numerical source: 805d9de27898b4a10e6212e65098d5995a40fdb1; packet parent
7b76b848650726c018567312b6526269af72496f. [INPUTS.json](INPUTS.json) binds 377
stored inputs/source files (14.54 MB); [EXTRA-INPUTS.json](EXTRA-INPUTS.json) binds
the original #273 archive/index used for zero/pedestal/noisy STAR readback.
All archives and members were read under Python -I; no untrusted archive code
was launched. Numerical helpers are explicitly selected from pinned reviewed
source. Complete global trajectories, polynomial coefficients, observation
tables, per-frame scores and sampling/signal diagnostics are in
[factorial.json](results/factorial.json). [STAR files](results/star/) are actual
roundtrip artifacts. [challenge.json](results/challenge.json) retains every
patch, derivative, Hessian and objective gain. [observation-geometry.json](results/observation-geometry.json)
is additive saved-result analysis performed after Part 2, without estimator
execution, tuning or score changes.

cpu64 hostname small-refmac-machine, affinity CPUs48–55 under nonblocking
/tmp/motioncorr-w5-cpu48-55.lock; NumPy2.5.3/Python3.12.3, all BLAS/OpenMP
thread counts one. Before each run the largest one-second assigned-CPU busy
fraction was .07 and .009901 respectively. Part1 exit0, Part2 exit0, all 18
factorial controls PASS. Native process count zero. Part1 launcher elapsed
2.00 s including admission; Part2 8.79 s including admission (not benchmarks).
Remote scratch /tmp/motioncorr-w5-20261025-7b76b848 occupied 16.58 MB after
Part2; including the two input tar files it remains under 40 MB, far below
10 GB. About 97.5 GB free at initial admission. Raw VM scratch and original
local W4 archives are retained. No unrelated process or service was touched.

Execution commands (once each):

```sh
ssh cpu64 'flock -n /tmp/motioncorr-w5-cpu48-55.lock taskset -c 48-55 ~/.mc-venv/bin/python -I -B /tmp/motioncorr-w5-20261025-7b76b848-launch.py'
ssh cpu64 'flock -n /tmp/motioncorr-w5-cpu48-55.lock taskset -c 48-55 ~/.mc-venv/bin/python -I -B /tmp/motioncorr-w5-20261025-7b76b848-factorial-launch.py'
```

Launchers and their exact hashes are retained under scripts/, FREEZE.json and
the results/*launch.json receipts. The two transferred input tar SHA256 values
are 07e1fd693dd536291d306dc430cf50fccf8f09b65d858f4c1812ea399226fe4f
and 9fcc73af133858de001b66def772c0cde49d7604464023306930fb43dedc03bd.
Local input-cache and transfer tar files are intentionally ignored by Git.
The six byte-exact copied native input STAR files (retained-*.star) are also
ignored; their authoritative originals remain in the hash-bound #273 archive.
All 64 generated estimator/control STAR artifacts are committed.
scripts/prepare.py stages the original archives and fixtures and deliberately
requires a detached worktree at packet parent7b76b848; place this W5 directory
in that checkout to rebuild the cache. scripts/prepare_extra.py reproduces the
supplemental export. Run common/challenge/intervention from the same directory
layout with the cache populated; outputs refuse overwrite. Reproduction must
use a fresh results directory and obey the currently assigned CPU/lock rules.
The initial staging-only wrong source filename was corrected before numerical
execution; it is disclosed in CHALLENGE-PROTOCOL.md. There were no numerical
retries. Reporting and supplemental preparation helpers were added after the
frozen computation; the scientific scripts and frozen records are unchanged.
'''
(R/'README.md').write_text(text)
data=[dict(case=k,arm=a,runtime=triple(v['runtime']),star=triple(v['STAR']),verdict=v['runtime']['verdict'])
      for k,rec in f['cases'].items() for a,v in rec['arms'].items()]
page='''<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:var(--font-sans,system-ui);color:var(--foreground,#222);margin:0;line-height:1.5}p{margin:0 0 12px}label{font-weight:600}select{font:inherit;color:inherit;background:var(--background,transparent);border:1px solid var(--border,#bbb);border-radius:6px;padding:5px;margin-left:8px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}th,td{text-align:left;padding:8px 5px;border-bottom:1px solid var(--border,#ddd)}th{font-size:12px;color:var(--muted-foreground,#666)}td:last-child{font-weight:600}.note{font-size:12px;color:var(--muted-foreground,#666);margin-top:10px}.wrap{overflow-x:auto}
</style></head><body><p><label>W5 field measurements <select id="pick"><option value="all">All cases</option>'''
page+=''.join(f'<option'+(' selected' if k=='affine' else '')+f'>{html.escape(k)}</option>' for k in f['cases'])
page+='''</select></label></p><div class="wrap"><table><thead><tr><th>Case / arm</th><th>Runtime RMS / p95 / max Å</th><th>STAR RMS / p95 / max Å</th><th>Gate</th></tr></thead><tbody id="rows"></tbody></table></div><p class="note">Limits: 0.20 / 0.40 / 0.80 Å. A00 inherited; A10 time only; A01 anchor only; A11 paired. Zero/pedestal use retained zero-state reconstructions; noisy is rounded-observation sensitivity. Full affine observations are captured at native precision.</p><script>const data='''+json.dumps(data)+''';function draw(){let s=document.getElementById('pick').value;document.getElementById('rows').innerHTML=data.filter(d=>s==='all'||d.case===s).map(d=>`<tr><td>${d.case} / ${d.arm}</td><td>${d.runtime}</td><td>${d.star}</td><td>${d.verdict}</td></tr>`).join('')}document.getElementById('pick').onchange=draw;draw();console.log('W5 rows',data.length);</script></body></html>'''
(R/'results/report.html').write_text(page)
print('Rendered README and HTML from saved results; 24 fixture-arm rows, 32 inherited probes.')
