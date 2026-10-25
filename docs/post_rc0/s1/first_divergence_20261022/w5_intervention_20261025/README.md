# W5 motion-truth challenge and one offline intervention

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

| Case | Arm | Runtime RMS / p95 / max Å | STAR RMS / p95 / max Å | Verdict |
|---|---|---|---|---|
| zero * | A00 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero * | A10 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero * | A01 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero * | A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| integer | A00 | 0.263614 / 0.431610 / 0.431610 | 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL |
| integer | A10 | 0.263614 / 0.431610 / 0.431610 | 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL |
| integer | A01 | 0.263614 / 0.431610 / 0.431610 | 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL |
| integer | A11 | 0.263614 / 0.431610 / 0.431610 | 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL |
| fractional | A00 | 0.524057 / 0.703417 / 0.703417 | 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL |
| fractional | A10 | 0.524057 / 0.703417 / 0.703417 | 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL |
| fractional | A01 | 0.524057 / 0.703417 / 0.703417 | 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL |
| fractional | A11 | 0.524057 / 0.703417 / 0.703417 | 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL |
| affine | A00 | 0.402437 / 0.742489 / 0.911068 | 0.402447 / 0.742491 / 0.911118 | FAIL/FAIL |
| affine | A10 | 0.366985 / 0.659382 / 0.752897 | 0.366972 / 0.659357 / 0.752894 | FAIL/FAIL |
| affine | A01 | 0.352627 / 0.701772 / 0.746488 | 0.352627 / 0.701760 / 0.746470 | FAIL/FAIL |
| affine | A11 | 0.317130 / 0.651866 / 0.688938 | 0.317127 / 0.651856 / 0.688940 | FAIL/FAIL |
| pedestal * | A00 | 2.119133 / 3.603757 / 3.893113 | 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL |
| pedestal * | A10 | 2.119133 / 3.603757 / 3.893113 | 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL |
| pedestal * | A01 | 2.119133 / 3.603757 / 3.893113 | 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL |
| pedestal * | A11 | 2.119133 / 3.603757 / 3.893113 | 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL |
| noisy * | A00 | 2.342955 / 4.376571 / 9.903901 | 2.342969 / 4.376601 / 9.903894 | FAIL/FAIL |
| noisy * | A10 | 3.634022 / 7.298261 / 19.941781 | 3.634026 / 7.298180 / 19.941822 | FAIL/FAIL |
| noisy * | A01 | 2.186840 / 4.264190 / 9.214298 | 2.186827 / 4.264195 / 9.214169 | FAIL/FAIL |
| noisy * | A11 | 3.481117 / 7.062906 / 19.241216 | 3.481104 / 7.062853 / 19.241128 | FAIL/FAIL |

The historical 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE ledger is unchanged. This
CPU experiment does not regrade CUDA. Flat/repeated remain UNIDENTIFIABLE and
are not converted into acceptance cases.

## Ideal observations through the identical fit

These use known centre observations only as diagnostic controls, never as
estimator recovery. Single-factor arms lose exact linear cancellation even
where the loose motion-truth limits still pass.

| Case | Arm | Runtime RMS / p95 / max Å | STAR RMS / p95 / max Å | Verdict |
|---|---|---|---|---|
| actual_global | A00 | 0.214314 / 0.303035 / 0.303035 | 0.214290 / 0.302919 / 0.302919 | FAIL/FAIL |
| actual_global | A10 | 0.150772 / 0.309565 / 0.398129 | 0.150781 / 0.309569 / 0.398143 | PASS/PASS |
| actual_global | A01 | 0.186462 / 0.265798 / 0.298602 | 0.186492 / 0.265995 / 0.298607 | PASS/PASS |
| actual_global | A11 | 0.085462 / 0.138034 / 0.138034 | 0.085462 / 0.138051 / 0.138051 | PASS/PASS |
| true_global | A00 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| true_global | A10 | 0.047682 / 0.094722 / 0.134731 | 0.047685 / 0.094733 / 0.134737 | PASS/PASS |
| true_global | A01 | 0.048316 / 0.096134 / 0.145610 | 0.048319 / 0.096132 / 0.145611 | PASS/PASS |
| true_global | A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |

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

| Case | Arm | Runtime RMS / p95 / max Å | STAR RMS / p95 / max Å | Verdict |
|---|---|---|---|---|
| vel0-N5-prod-5it | A00=A10=A01=A11 | 0.404234 / 0.575495 / 0.575495 | 0.404233 / 0.575496 / 0.575496 | FAIL/FAIL |
| vel0-N5-prod-50it | A00=A10=A01=A11 | 0.346874 / 0.516099 / 0.516099 | 0.346874 / 0.516099 / 0.516099 | FAIL/FAIL |
| vel0-N5-iso-5it | A00=A10=A01=A11 | 0.034667 / 0.059405 / 0.059405 | 0.034667 / 0.059403 / 0.059403 | PASS/PASS |
| vel0-N5-iso-50it | A00=A10=A01=A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N9-prod-5it | A00=A10=A01=A11 | 0.424674 / 0.652407 / 0.652407 | 0.424674 / 0.652410 / 0.652410 | FAIL/FAIL |
| vel0-N9-prod-50it | A00=A10=A01=A11 | 0.038813 / 0.085346 / 0.085346 | 0.038814 / 0.085349 / 0.085349 | PASS/PASS |
| vel0-N9-iso-5it | A00=A10=A01=A11 | 0.023075 / 0.042043 / 0.042043 | 0.023075 / 0.042044 / 0.042044 | PASS/PASS |
| vel0-N9-iso-50it | A00=A10=A01=A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N13-prod-5it | A00=A10=A01=A11 | 0.283158 / 0.408437 / 0.408437 | 0.283157 / 0.408437 / 0.408437 | FAIL/FAIL |
| vel0-N13-prod-50it | A00=A10=A01=A11 | 0.001487 / 0.002924 / 0.002924 | 0.001487 / 0.002923 / 0.002923 | PASS/PASS |
| vel0-N13-iso-5it | A00=A10=A01=A11 | 0.026400 / 0.043843 / 0.043843 | 0.026401 / 0.043843 / 0.043843 | PASS/PASS |
| vel0-N13-iso-50it | A00=A10=A01=A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N20-prod-5it | A00=A10=A01=A11 | 0.303939 / 0.461294 / 0.488578 | 0.303939 / 0.461294 / 0.488578 | FAIL/FAIL |
| vel0-N20-prod-50it | A00=A10=A01=A11 | 0.000093 / 0.000159 / 0.000168 | 0.000093 / 0.000159 / 0.000170 | PASS/PASS |
| vel0-N20-iso-5it | A00=A10=A01=A11 | 0.036315 / 0.053713 / 0.060335 | 0.036315 / 0.053709 / 0.060338 | PASS/PASS |
| vel0-N20-iso-50it | A00=A10=A01=A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N5-prod-5it | A00=A10=A01=A11 | 0.326485 / 0.522136 / 0.522136 | 0.326486 / 0.522137 / 0.522137 | FAIL/FAIL |
| vel1-N5-prod-50it | A00=A10=A01=A11 | 0.347409 / 0.532028 / 0.532028 | 0.347410 / 0.532029 / 0.532029 | FAIL/FAIL |
| vel1-N5-iso-5it | A00=A10=A01=A11 | 0.042961 / 0.067406 / 0.067406 | 0.042962 / 0.067408 / 0.067408 | PASS/PASS |
| vel1-N5-iso-50it | A00=A10=A01=A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N9-prod-5it | A00=A10=A01=A11 | 0.392386 / 0.646857 / 0.646857 | 0.392386 / 0.646859 / 0.646859 | FAIL/FAIL |
| vel1-N9-prod-50it | A00=A10=A01=A11 | 0.059364 / 0.097360 / 0.097360 | 0.059364 / 0.097362 / 0.097362 | PASS/PASS |
| vel1-N9-iso-5it | A00=A10=A01=A11 | 0.035836 / 0.061860 / 0.061860 | 0.035836 / 0.061862 / 0.061862 | PASS/PASS |
| vel1-N9-iso-50it | A00=A10=A01=A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N13-prod-5it | A00=A10=A01=A11 | 0.237302 / 0.353393 / 0.353393 | 0.237301 / 0.353394 / 0.353394 | FAIL/FAIL |
| vel1-N13-prod-50it | A00=A10=A01=A11 | 0.000875 / 0.001601 / 0.001601 | 0.000875 / 0.001603 / 0.001603 | PASS/PASS |
| vel1-N13-iso-5it | A00=A10=A01=A11 | 0.023846 / 0.036916 / 0.036916 | 0.023846 / 0.036914 / 0.036914 | PASS/PASS |
| vel1-N13-iso-50it | A00=A10=A01=A11 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N20-prod-5it | A00=A10=A01=A11 | 0.246960 / 0.370794 / 0.522069 | 0.246961 / 0.370796 / 0.522071 | FAIL/FAIL |
| vel1-N20-prod-50it | A00=A10=A01=A11 | 0.000038 / 0.000061 / 0.000061 | 0.000038 / 0.000063 / 0.000063 | PASS/PASS |
| vel1-N20-iso-5it | A00=A10=A01=A11 | 10.472048 / 14.810680 / 14.811067 | 10.472049 / 14.810683 / 14.811072 | FAIL/FAIL |
| vel1-N20-iso-50it | A00=A10=A01=A11 | 10.467457 / 14.803220 / 14.803220 | 10.467457 / 14.803220 / 14.803220 | FAIL/FAIL |

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
