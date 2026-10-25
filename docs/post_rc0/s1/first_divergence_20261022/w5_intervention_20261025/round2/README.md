# W5 Round 2: global dynamics and iterative de-warping

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

| Fixture | Arm | Runtime RMS / p95 / max Å | STAR RMS / p95 / max Å | Status |
|---|---|---|---|---|
| zero | double-gain1-5it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero | double-gain1-50it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero | double-gain0.5-5it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero | double-gain0.5-50it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero | map32-gain1-5it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero | map32-gain1-50it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero | map32-gain0.5-5it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| zero | map32-gain0.5-50it | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| integer | double-gain1-5it | 0.436648 / 0.589666 / 0.589666 | 0.436648 / 0.589667 / 0.589667 | FAIL/FAIL |
| integer | double-gain1-50it | 0.268057 / 0.365527 / 0.365527 | 0.268056 / 0.365526 / 0.365526 | FAIL/FAIL |
| integer | double-gain0.5-5it | 0.330736 / 0.521850 / 0.521850 | 0.330736 / 0.521850 / 0.521850 | FAIL/FAIL |
| integer | double-gain0.5-50it | 0.000180 / 0.000284 / 0.000284 | 0.000179 / 0.000282 / 0.000282 | PASS/PASS |
| integer | map32-gain1-5it | 0.308339 / 0.490385 / 0.490385 | 0.308340 / 0.490385 / 0.490385 | FAIL/FAIL |
| integer | map32-gain1-50it | 0.265115 / 0.356630 / 0.356630 | 0.265115 / 0.356627 / 0.356627 | FAIL/FAIL |
| integer | map32-gain0.5-5it | 0.181790 / 0.244429 / 0.244429 | 0.181792 / 0.244431 / 0.244431 | PASS/PASS |
| integer | map32-gain0.5-50it | 0.073975 / 0.115201 / 0.115201 | 0.073974 / 0.115199 / 0.115199 | PASS/PASS |
| fractional | double-gain1-5it | 0.326485 / 0.522136 / 0.522136 | 0.326485 / 0.522136 / 0.522136 | FAIL/FAIL |
| fractional | double-gain1-50it | 0.347616 / 0.531522 / 0.531522 | 0.347617 / 0.531523 / 0.531523 | FAIL/FAIL |
| fractional | double-gain0.5-5it | 0.177840 / 0.293386 / 0.293386 | 0.177839 / 0.293385 / 0.293385 | PASS/PASS |
| fractional | double-gain0.5-50it | 0.000082 / 0.000136 / 0.000136 | 0.000082 / 0.000135 / 0.000135 | PASS/PASS |
| fractional | map32-gain1-5it | 0.431639 / 0.615639 / 0.615639 | 0.431638 / 0.615636 / 0.615636 | FAIL/FAIL |
| fractional | map32-gain1-50it | 0.081461 / 0.139474 / 0.139474 | 0.081462 / 0.139475 / 0.139475 | PASS/PASS |
| fractional | map32-gain0.5-5it | 0.260018 / 0.435231 / 0.435231 | 0.260017 / 0.435229 / 0.435229 | FAIL/FAIL |
| fractional | map32-gain0.5-50it | 0.104588 / 0.163514 / 0.163514 | 0.104587 / 0.163513 / 0.163513 | PASS/PASS |
| affine | double-gain1-5it | 0.320006 / 0.588199 / 0.887412 | 0.319982 / 0.588153 / 0.887327 | FAIL/FAIL |
| affine | double-gain1-50it | 0.326376 / 0.637785 / 1.145827 | 0.326376 / 0.637784 / 1.145825 | FAIL/FAIL |
| affine | double-gain0.5-5it | 0.189674 / 0.385192 / 0.524476 | 0.189661 / 0.385161 / 0.524339 | PASS/PASS |
| affine | double-gain0.5-50it | 0.262779 / 0.578429 / 1.033354 | 0.262779 / 0.578427 / 1.033352 | FAIL/FAIL |
| affine | map32-gain1-5it | 0.263833 / 0.447615 / 0.893394 | 0.263831 / 0.447612 / 0.893466 | FAIL/FAIL |
| affine | map32-gain1-50it | 0.303507 / 0.621426 / 1.095039 | 0.303507 / 0.621423 / 1.095042 | FAIL/FAIL |
| affine | map32-gain0.5-5it | 0.200436 / 0.342332 / 0.619227 | 0.200414 / 0.342367 / 0.619262 | FAIL/FAIL |
| affine | map32-gain0.5-50it | 0.288536 / 0.601056 / 1.046198 | 0.288536 / 0.601056 / 1.046199 | FAIL/FAIL |
| pedestal | double-gain1-5it | 0.319928 / 0.588168 / 0.887250 | 0.319956 / 0.588221 / 0.887350 | FAIL/FAIL |
| pedestal | double-gain1-50it | 0.445414 / 0.752559 / 1.184846 | 0.445414 / 0.752562 / 1.184849 | FAIL/FAIL |
| pedestal | double-gain0.5-5it | 0.189677 / 0.385150 / 0.524638 | 0.189686 / 0.385189 / 0.524683 | PASS/PASS |
| pedestal | double-gain0.5-50it | 0.262777 / 0.578416 / 1.033341 | 0.262777 / 0.578418 / 1.033338 | FAIL/FAIL |
| pedestal | map32-gain1-5it | 3.942380 / 7.405338 / 12.560416 | 3.942379 / 7.405335 / 12.560413 | FAIL/FAIL |
| pedestal | map32-gain1-50it | 3.942380 / 7.405338 / 12.560416 | 3.942379 / 7.405335 / 12.560413 | FAIL/FAIL |
| pedestal | map32-gain0.5-5it | 3.942380 / 7.405338 / 12.560416 | 3.942379 / 7.405335 / 12.560413 | FAIL/FAIL |
| pedestal | map32-gain0.5-50it | 3.942380 / 7.405338 / 12.560416 | 3.942379 / 7.405335 / 12.560413 | FAIL/FAIL |
| noisy | double-gain1-5it | 1.668452 / 3.319727 / 7.136670 | 1.668436 / 3.319627 / 7.136601 | FAIL/FAIL |
| noisy | double-gain1-50it | 0.698054 / 1.383114 / 1.641771 | 0.698055 / 1.383115 / 1.641771 | FAIL/FAIL |
| noisy | double-gain0.5-5it | 3.049155 / 6.398229 / 21.492574 | 3.049152 / 6.398137 / 21.492520 | FAIL/FAIL |
| noisy | double-gain0.5-50it | 0.870770 / 1.695223 / 1.956240 | 0.870770 / 1.695222 / 1.956241 | FAIL/FAIL |
| noisy | map32-gain1-5it | 1.635645 / 3.299993 / 7.780081 | 1.635658 / 3.300061 / 7.780230 | FAIL/FAIL |
| noisy | map32-gain1-50it | 0.880546 / 1.681561 / 1.999239 | 0.880545 / 1.681557 / 1.999235 | FAIL/FAIL |
| noisy | map32-gain0.5-5it | 1.744475 / 3.204997 / 7.870129 | 1.744487 / 3.204797 / 7.870369 | FAIL/FAIL |
| noisy | map32-gain0.5-50it | 0.843461 / 1.707320 / 1.985870 | 0.843462 / 1.707323 / 1.985869 | FAIL/FAIL |
| flat | double-gain1-5it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| flat | double-gain1-50it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| flat | double-gain0.5-5it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| flat | double-gain0.5-50it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| flat | map32-gain1-5it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| flat | map32-gain1-50it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| flat | map32-gain0.5-5it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| flat | map32-gain0.5-50it | 2.104421 / 3.436505 / 3.436505 | 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE |
| repeated | double-gain1-5it | 9.012581 / 14.197954 / 14.197954 | 9.012581 / 14.197954 / 14.197954 | UNIDENTIFIABLE |
| repeated | double-gain1-50it | 9.029315 / 14.230077 / 14.230077 | 9.029315 / 14.230077 / 14.230077 | UNIDENTIFIABLE |
| repeated | double-gain0.5-5it | 6.898739 / 8.985501 / 8.985501 | 6.898739 / 8.985500 / 8.985500 | UNIDENTIFIABLE |
| repeated | double-gain0.5-50it | 4.339040 / 5.718833 / 5.718833 | 4.339040 / 5.718833 / 5.718833 | UNIDENTIFIABLE |
| repeated | map32-gain1-5it | 16.533858 / 28.003916 / 28.003916 | 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE |
| repeated | map32-gain1-50it | 16.607416 / 28.003916 / 28.003916 | 16.607416 / 28.003916 / 28.003916 | UNIDENTIFIABLE |
| repeated | map32-gain0.5-5it | 6.740209 / 8.831312 / 8.831312 | 6.740209 / 8.831312 / 8.831312 | UNIDENTIFIABLE |
| repeated | map32-gain0.5-50it | 4.395413 / 5.842215 / 5.842215 | 4.395413 / 5.842215 / 5.842215 | UNIDENTIFIABLE |

## E1 N controls, both stop rules and weights

Vel0=(-1,2), vel1=(-.8125,.53125) px/frame. These are the retained periodic
phase-ramp controls, not new gate-role image fixtures. Their global trajectories
define the entire applied field; some long trajectories put even truth outside
the finite detector ROI. Numeric field PASS is not an image/sampling PASS.
Every gain1 phase baseline matches W5 exactly, including the harmful row.

| Control / gain / stop | Runtime RMS / p95 / max Å | STAR RMS / p95 / max Å | Field status |
|---|---|---|---|
| vel0-N5-prod-gain1-5it | 0.404234 / 0.575495 / 0.575495 | 0.404233 / 0.575496 / 0.575496 | FAIL/FAIL |
| vel0-N5-prod-gain1-50it | 0.346874 / 0.516099 / 0.516099 | 0.346874 / 0.516099 / 0.516099 | FAIL/FAIL |
| vel0-N5-prod-gain0.5-5it | 0.467552 / 0.688445 / 0.688445 | 0.467552 / 0.688445 / 0.688445 | FAIL/FAIL |
| vel0-N5-prod-gain0.5-50it | 0.000255 / 0.000376 / 0.000376 | 0.000255 / 0.000374 / 0.000374 | PASS/PASS |
| vel0-N5-iso-gain1-5it | 0.034667 / 0.059405 / 0.059405 | 0.034667 / 0.059403 / 0.059403 | PASS/PASS |
| vel0-N5-iso-gain1-50it | 2.108e-10 / 3.531e-10 / 3.531e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N5-iso-gain0.5-5it | 0.135571 / 0.219535 / 0.219535 | 0.135571 / 0.219534 / 0.219534 | PASS/PASS |
| vel0-N5-iso-gain0.5-50it | 2.652e-10 / 4.233e-10 / 4.233e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N9-prod-gain1-5it | 0.424674 / 0.652407 / 0.652407 | 0.424674 / 0.652410 / 0.652410 | FAIL/FAIL |
| vel0-N9-prod-gain1-50it | 0.038813 / 0.085346 / 0.085346 | 0.038814 / 0.085349 / 0.085349 | PASS/PASS |
| vel0-N9-prod-gain0.5-5it | 0.324917 / 0.605253 / 0.605253 | 0.324917 / 0.605251 / 0.605251 | FAIL/FAIL |
| vel0-N9-prod-gain0.5-50it | 0.000461 / 0.000859 / 0.000859 | 0.000461 / 0.000860 / 0.000860 | PASS/PASS |
| vel0-N9-iso-gain1-5it | 0.023075 / 0.042043 / 0.042043 | 0.023075 / 0.042044 / 0.042044 | PASS/PASS |
| vel0-N9-iso-gain1-50it | 1.181e-10 / 2.047e-10 / 2.047e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N9-iso-gain0.5-5it | 0.190357 / 0.319930 / 0.319930 | 0.190358 / 0.319931 / 0.319931 | PASS/PASS |
| vel0-N9-iso-gain0.5-50it | 5.016e-10 / 8.254e-10 / 8.254e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N13-prod-gain1-5it | 0.283158 / 0.408437 / 0.408437 | 0.283157 / 0.408437 / 0.408437 | FAIL/FAIL |
| vel0-N13-prod-gain1-50it | 0.001487 / 0.002924 / 0.002924 | 0.001487 / 0.002923 / 0.002923 | PASS/PASS |
| vel0-N13-prod-gain0.5-5it | 0.284017 / 0.620054 / 0.620054 | 0.284018 / 0.620057 / 0.620057 | FAIL/FAIL |
| vel0-N13-prod-gain0.5-50it | 0.000523 / 0.001142 / 0.001142 | 0.000523 / 0.001141 / 0.001141 | PASS/PASS |
| vel0-N13-iso-gain1-5it | 0.026400 / 0.043843 / 0.043843 | 0.026401 / 0.043843 / 0.043843 | PASS/PASS |
| vel0-N13-iso-gain1-50it | 1.744e-10 / 3.827e-10 / 3.827e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N13-iso-gain0.5-5it | 0.214886 / 0.526442 / 0.526442 | 0.214886 / 0.526444 / 0.526444 | FAIL/FAIL |
| vel0-N13-iso-gain0.5-50it | 5.768e-10 / 1.437e-09 / 1.437e-09 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N20-prod-gain1-5it | 0.303939 / 0.461294 / 0.488578 | 0.303939 / 0.461294 / 0.488578 | FAIL/FAIL |
| vel0-N20-prod-gain1-50it | 0.000093 / 0.000159 / 0.000168 | 0.000093 / 0.000159 / 0.000170 | PASS/PASS |
| vel0-N20-prod-gain0.5-5it | 0.439490 / 0.729942 / 0.838566 | 0.439490 / 0.729943 / 0.838564 | FAIL/FAIL |
| vel0-N20-prod-gain0.5-50it | 0.000963 / 0.001493 / 0.001876 | 0.000962 / 0.001493 / 0.001873 | PASS/PASS |
| vel0-N20-iso-gain1-5it | 0.036315 / 0.053713 / 0.060335 | 0.036315 / 0.053709 / 0.060338 | PASS/PASS |
| vel0-N20-iso-gain1-50it | 1.133e-10 / 1.493e-10 / 2.274e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel0-N20-iso-gain0.5-5it | 0.302964 / 0.474278 / 0.515429 | 0.302963 / 0.474278 / 0.515428 | FAIL/FAIL |
| vel0-N20-iso-gain0.5-50it | 4.740e-10 / 8.787e-10 / 9.817e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N5-prod-gain1-5it | 0.326485 / 0.522136 / 0.522136 | 0.326486 / 0.522137 / 0.522137 | FAIL/FAIL |
| vel1-N5-prod-gain1-50it | 0.347409 / 0.532028 / 0.532028 | 0.347410 / 0.532029 / 0.532029 | FAIL/FAIL |
| vel1-N5-prod-gain0.5-5it | 0.177840 / 0.293386 / 0.293386 | 0.177839 / 0.293385 / 0.293385 | PASS/PASS |
| vel1-N5-prod-gain0.5-50it | 0.000082 / 0.000136 / 0.000136 | 0.000081 / 0.000134 / 0.000134 | PASS/PASS |
| vel1-N5-iso-gain1-5it | 0.042961 / 0.067406 / 0.067406 | 0.042962 / 0.067408 / 0.067408 | PASS/PASS |
| vel1-N5-iso-gain1-50it | 2.895e-10 / 4.276e-10 / 4.276e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N5-iso-gain0.5-5it | 0.135049 / 0.212475 / 0.212475 | 0.135049 / 0.212476 / 0.212476 | PASS/PASS |
| vel1-N5-iso-gain0.5-50it | 2.531e-10 / 3.722e-10 / 3.722e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N9-prod-gain1-5it | 0.392386 / 0.646857 / 0.646857 | 0.392386 / 0.646859 / 0.646859 | FAIL/FAIL |
| vel1-N9-prod-gain1-50it | 0.059364 / 0.097360 / 0.097360 | 0.059364 / 0.097362 / 0.097362 | PASS/PASS |
| vel1-N9-prod-gain0.5-5it | 0.171062 / 0.327834 / 0.327834 | 0.171062 / 0.327833 / 0.327833 | PASS/PASS |
| vel1-N9-prod-gain0.5-50it | 0.000210 / 0.000402 / 0.000402 | 0.000210 / 0.000400 / 0.000400 | PASS/PASS |
| vel1-N9-iso-gain1-5it | 0.035836 / 0.061860 / 0.061860 | 0.035836 / 0.061862 / 0.061862 | PASS/PASS |
| vel1-N9-iso-gain1-50it | 1.576e-10 / 2.487e-10 / 2.487e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N9-iso-gain0.5-5it | 0.169299 / 0.274359 / 0.274359 | 0.169300 / 0.274360 / 0.274360 | PASS/PASS |
| vel1-N9-iso-gain0.5-50it | 4.797e-10 / 7.834e-10 / 7.834e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N13-prod-gain1-5it | 0.237302 / 0.353393 / 0.353393 | 0.237301 / 0.353394 / 0.353394 | FAIL/FAIL |
| vel1-N13-prod-gain1-50it | 0.000875 / 0.001601 / 0.001601 | 0.000875 / 0.001603 / 0.001603 | PASS/PASS |
| vel1-N13-prod-gain0.5-5it | 0.402256 / 0.691201 / 0.691201 | 0.402257 / 0.691200 / 0.691200 | FAIL/FAIL |
| vel1-N13-prod-gain0.5-50it | 0.000644 / 0.001107 / 0.001107 | 0.000645 / 0.001104 / 0.001104 | PASS/PASS |
| vel1-N13-iso-gain1-5it | 0.023846 / 0.036916 / 0.036916 | 0.023846 / 0.036914 / 0.036914 | PASS/PASS |
| vel1-N13-iso-gain1-50it | 1.811e-10 / 3.046e-10 / 3.046e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N13-iso-gain0.5-5it | 0.192154 / 0.331135 / 0.331135 | 0.192154 / 0.331138 / 0.331138 | PASS/PASS |
| vel1-N13-iso-gain0.5-50it | 5.628e-10 / 9.445e-10 / 9.445e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |
| vel1-N20-prod-gain1-5it | 0.246960 / 0.370794 / 0.522069 | 0.246961 / 0.370796 / 0.522071 | FAIL/FAIL |
| vel1-N20-prod-gain1-50it | 0.000038 / 0.000061 / 0.000061 | 0.000038 / 0.000063 / 0.000063 | PASS/PASS |
| vel1-N20-prod-gain0.5-5it | 0.303739 / 0.556220 / 0.614151 | 0.303739 / 0.556217 / 0.614148 | FAIL/FAIL |
| vel1-N20-prod-gain0.5-50it | 0.000678 / 0.001241 / 0.001370 | 0.000678 / 0.001241 / 0.001368 | PASS/PASS |
| vel1-N20-iso-gain1-5it | 10.472048 / 14.810680 / 14.811067 | 10.472049 / 14.810683 / 14.811072 | FAIL/FAIL |
| vel1-N20-iso-gain1-50it | 10.467457 / 14.803220 / 14.803220 | 10.467457 / 14.803220 / 14.803220 | FAIL/FAIL |
| vel1-N20-iso-gain0.5-5it | 0.346672 / 0.517893 / 0.631687 | 0.346671 / 0.517891 / 0.631687 | FAIL/FAIL |
| vel1-N20-iso-gain0.5-50it | 4.662e-10 / 6.580e-10 / 8.237e-10 | 0.000000 / 0.000000 / 0.000000 | PASS/PASS |

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

| Vel | N | Gain | Runtime term RMS / p95 / max Å | STAR term RMS / p95 / max Å | 5-stop truth RMS Å | 50-stop truth RMS Å |
|---|---|---|---|---|---|---|
| 0 | 9 | 1.0 | 0.437295 / 0.653839 / 0.653839 | 0.437295 / 0.653843 / 0.653843 | 0.424674 | 0.038813 |
| 0 | 9 | 0.5 | 0.324456 / 0.604394 / 0.604394 | 0.324456 / 0.604391 / 0.604391 | 0.324917 | 0.000461 |
| 0 | 13 | 1.0 | 0.282162 / 0.408025 / 0.408025 | 0.282162 / 0.408025 / 0.408025 | 0.283158 | 0.001487 |
| 0 | 13 | 0.5 | 0.283494 / 0.618912 / 0.618912 | 0.283495 / 0.618916 / 0.618916 | 0.284017 | 0.000523 |
| 0 | 20 | 1.0 | 0.303871 / 0.461167 / 0.488444 | 0.303871 / 0.461167 / 0.488444 | 0.303939 | 0.000093 |
| 0 | 20 | 0.5 | 0.438543 / 0.728523 / 0.836690 | 0.438543 / 0.728524 / 0.836691 | 0.439490 | 0.000963 |
| 1 | 9 | 1.0 | 0.429600 / 0.664318 / 0.664318 | 0.429601 / 0.664322 / 0.664322 | 0.392386 | 0.059364 |
| 1 | 9 | 0.5 | 0.170852 / 0.327432 / 0.327432 | 0.170852 / 0.327433 / 0.327433 | 0.171062 | 0.000210 |
| 1 | 13 | 1.0 | 0.237723 / 0.354250 / 0.354250 | 0.237721 / 0.354255 / 0.354255 | 0.237302 | 0.000875 |
| 1 | 13 | 0.5 | 0.401612 / 0.690094 / 0.690094 | 0.401612 / 0.690095 / 0.690095 | 0.402256 | 0.000644 |
| 1 | 20 | 1.0 | 0.246975 / 0.370811 / 0.522075 | 0.246976 / 0.370814 / 0.522078 | 0.246960 | 0.000038 |
| 1 | 20 | 0.5 | 0.303062 / 0.554979 / 0.612781 | 0.303061 / 0.554977 / 0.612780 | 0.303739 | 0.000678 |

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

| E2 arm | Iteration | Runtime RMS / p95 / max Å | STAR RMS / p95 / max Å | Field status |
|---|---|---|---|---|
| stored-native-start | 0 | 0.402437 / 0.742489 / 0.911068 | 0.402447 / 0.742491 / 0.911118 | FAIL/FAIL |
| stored-native-start | 1 | 0.288939 / 0.506042 / 0.972283 | 0.288935 / 0.506051 / 0.972295 | FAIL/FAIL |
| stored-native-start | 2 | 0.195318 / 0.374228 / 0.724710 | 0.195328 / 0.374244 / 0.724779 | PASS/PASS |
| stored-native-start | 3 | 0.163701 / 0.294091 / 0.582089 | 0.163705 / 0.294081 / 0.582098 | PASS/PASS |
| stored-native-start | 4 | 0.172311 / 0.316825 / 0.461877 | 0.172330 / 0.316824 / 0.461868 | PASS/PASS |
| stored-native-start | 5 | 0.167942 / 0.281414 / 0.410660 | 0.167956 / 0.281442 / 0.410626 | PASS/PASS |
| stored-native-start | 6 | 0.224575 / 0.449777 / 0.595660 | 0.224567 / 0.449771 / 0.595654 | FAIL/FAIL |
| stored-native-start | 7 | 0.213195 / 0.445557 / 0.512302 | 0.213166 / 0.445541 / 0.512267 | FAIL/FAIL |
| stored-native-start | 8 | 0.155705 / 0.291062 / 0.460542 | 0.155692 / 0.291056 / 0.460523 | PASS/PASS |
| stored-native-start | 9 | 0.143526 / 0.242240 / 0.329584 | 0.143503 / 0.242192 / 0.329580 | PASS/PASS |
| stored-native-start | 10 | 0.144337 / 0.287736 / 0.465760 | 0.144323 / 0.287738 / 0.465742 | PASS/PASS |
| stored-native-start | 11 | 0.149771 / 0.247736 / 0.312743 | 0.149752 / 0.247680 / 0.312769 | PASS/PASS |
| stored-native-start | 12 | 0.173972 / 0.327863 / 0.408680 | 0.173963 / 0.327863 / 0.408696 | PASS/PASS |
| oracle-native-start | 0 | 0.402437 / 0.742489 / 0.911068 | 0.402447 / 0.742491 / 0.911118 | FAIL/FAIL |
| oracle-native-start | 1 | 0.267599 / 0.469819 / 0.694420 | 0.267616 / 0.469825 / 0.694447 | FAIL/FAIL |
| oracle-native-start | 2 | 0.171204 / 0.284875 / 0.587252 | 0.171213 / 0.284810 / 0.587383 | PASS/PASS |
| oracle-native-start | 3 | 0.183466 / 0.355388 / 0.402644 | 0.183492 / 0.355403 / 0.402675 | PASS/PASS |
| oracle-native-start | 4 | 0.174958 / 0.341446 / 0.368457 | 0.174939 / 0.341440 / 0.368441 | PASS/PASS |
| oracle-native-start | 5 | 0.243059 / 0.406414 / 0.409312 | 0.243110 / 0.406452 / 0.409349 | FAIL/FAIL |
| oracle-native-start | 6 | 0.169700 / 0.266945 / 0.482245 | 0.169715 / 0.267001 / 0.482052 | PASS/PASS |
| oracle-native-start | 7 | 0.120751 / 0.183892 / 0.471523 | 0.120730 / 0.183854 / 0.471611 | PASS/PASS |
| oracle-native-start | 8 | 0.087482 / 0.153887 / 0.190002 | 0.087521 / 0.153910 / 0.190279 | PASS/PASS |
| oracle-native-start | 9 | 0.094251 / 0.178593 / 0.182374 | 0.094243 / 0.178571 / 0.182356 | PASS/PASS |
| oracle-native-start | 10 | 0.098674 / 0.180699 / 0.190872 | 0.098671 / 0.180685 / 0.190860 | PASS/PASS |
| oracle-native-start | 11 | 0.120990 / 0.228216 / 0.233810 | 0.120986 / 0.228211 / 0.233813 | PASS/PASS |
| oracle-native-start | 12 | 0.138888 / 0.258565 / 0.267886 | 0.138873 / 0.258542 / 0.267859 | PASS/PASS |

Control/robustness summary (full per-iteration records are linked above):

| Arm | First update RMS px | Iteration12 runtime RMS / p95 / max Å | Iteration12 STAR RMS / p95 / max Å |
|---|---|---|---|
| stored-native-start | 0.336914 | 0.173972 / 0.327863 / 0.408680 | 0.173963 / 0.327863 / 0.408696 |
| stored-truth-trivial | 0.035505 | 0.100219 / 0.169024 / 0.272041 | 0.100295 / 0.169133 / 0.272093 |
| stored-wrong-sign | 4.296059 | 120.558587 / 219.465209 / 261.271659 | 120.558616 / 219.465210 / 261.271660 |
| stored-wrong-start-robustness | 4.296059 | 0.160147 / 0.252788 / 0.341173 | 0.160096 / 0.252685 / 0.341038 |
| stored-zero | 0.000000 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |
| oracle-native-start | 0.329489 | 0.138888 / 0.258565 / 0.267886 | 0.138873 / 0.258542 / 0.267859 |
| oracle-truth-trivial | 0.000000 | 4.134e-15 / 7.958e-15 / 1.403e-14 | 5.091e-15 / 9.896e-15 / 1.877e-14 |
| oracle-wrong-sign | 4.333499 | 344.460619 / 445.434506 / 462.453042 | 344.460621 / 445.434531 / 462.453087 |
| oracle-wrong-start-robustness | 4.333499 | 0.132821 / 0.190152 / 0.232043 | 0.132829 / 0.190145 / 0.232000 |
| oracle-zero | 0.000000 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |

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

| Input | Start x,y | 50-step error RMS px | 500-step error RMS px | Endpoint update RMS px | Diagnostic label |
|---|---|---|---|---|---|
| phase-vel0 | 0,0 | 0.391948 | 0.283853 | 0.435449 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel0 | 0,0.5 | 0.387484 | 0.276041 | 0.588380 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel0 | 0,1 | 0.195741 | 0.633550 | 0.526373 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel0 | 0.5,0 | 0.344598 | 0.283945 | 0.393712 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel0 | 0.5,0.5 | 0.454125 | 0.348591 | 0.691190 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel0 | 0.5,1 | 0.320174 | 0.161429 | 0.305380 | SLOW_OR_IRREGULAR_CONVERGENCE |
| phase-vel0 | 1,0 | 0.288892 | 0.324425 | 0.551830 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel0 | 1,0.5 | 0.365055 | 0.264354 | 0.460040 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel0 | 1,1 | 0.000000 | 0.000000 | 0.000000 | FIXED_POINT |
| phase-vel1 | 0,0 | 0.392553 | 0.480402 | 0.739949 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel1 | 0,0.5 | 0.511577 | 0.171900 | 0.292562 | SLOW_OR_IRREGULAR_CONVERGENCE |
| phase-vel1 | 0,1 | 0.827297 | 0.219718 | 0.381080 | SLOW_OR_IRREGULAR_CONVERGENCE |
| phase-vel1 | 0.5,0 | 0.520477 | 0.284033 | 0.466717 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel1 | 0.5,0.5 | 0.335798 | 0.297793 | 0.445109 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel1 | 0.5,1 | 0.351288 | 0.199288 | 0.390607 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel1 | 1,0 | 0.594342 | 0.169685 | 0.219712 | SLOW_OR_IRREGULAR_CONVERGENCE |
| phase-vel1 | 1,0.5 | 0.444128 | 0.339684 | 0.563932 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| phase-vel1 | 1,1 | 0.000000 | 0.000000 | 0.000000 | FIXED_POINT |
| fixture-integer | 0,0 | 0.302889 | 0.358880 | 0.613469 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-integer | 0,0.5 | 0.332249 | 0.417408 | 0.790195 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-integer | 0,1 | 0.312578 | 0.340008 | 0.550492 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-integer | 0.5,0 | 0.344636 | 0.293399 | 0.610198 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-integer | 0.5,0.5 | 0.454174 | 0.237501 | 0.519007 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-integer | 0.5,1 | 0.320215 | 0.190588 | 0.393991 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-integer | 1,0 | 0.288844 | 0.505831 | 0.520952 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-integer | 1,0.5 | 0.784554 | 0.391398 | 0.716831 | SLOW_OR_IRREGULAR_CONVERGENCE |
| fixture-integer | 1,1 | 0.000052 | 0.057395 | 0.125322 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-fractional | 0,0 | 0.392787 | 0.252405 | 0.390646 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-fractional | 0,0.5 | 0.511233 | 0.205092 | 0.437654 | SLOW_OR_IRREGULAR_CONVERGENCE |
| fixture-fractional | 0,1 | 0.827604 | 0.385259 | 0.405777 | SLOW_OR_IRREGULAR_CONVERGENCE |
| fixture-fractional | 0.5,0 | 0.520648 | 0.226428 | 0.352442 | SLOW_OR_IRREGULAR_CONVERGENCE |
| fixture-fractional | 0.5,0.5 | 0.335949 | 0.295661 | 0.646228 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-fractional | 0.5,1 | 0.350475 | 0.284149 | 0.574329 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-fractional | 1,0 | 0.594275 | 0.257934 | 0.242938 | SLOW_OR_IRREGULAR_CONVERGENCE |
| fixture-fractional | 1,0.5 | 0.444880 | 0.418301 | 0.680596 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
| fixture-fractional | 1,1 | 0.001126 | 0.300128 | 0.641980 | NONSTATIONARY_NO_SMALL_PERIOD_CERTIFIED |
