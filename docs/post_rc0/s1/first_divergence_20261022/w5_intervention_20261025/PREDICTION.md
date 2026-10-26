# Frozen W5 intervention prediction

Recorded after Part 1, before the factorial computation. Part 1 output SHA256
is recorded in FREEZE.json together with this file and the scripts before launch.

The truth-aligned sum-of-others test gives 0.343210 px anchored update RMS;
W4's fixed point reproduces at 0.2749065 px from truth. Its three references did
not test stationarity at truth. The pure-translation controls pass. Thus objective
bias is present; a wrong basin or stopping alone cannot explain this residual.
Spatial observation mismatch and convention distortion can coexist with it.

Chosen intervention: unit-group local observations use the actual frame index
and frame-zero sample, rather than a half-frame index and extrapolated zero-time
sample. This is a coupled time/anchor convention; the final field gauge remains
fixed frame zero, with no post-fit registration. No peak/weight/window/global
estimator/patch acceptance change. No model-capacity floor is subtracted.

Factorial: A00 uses z=f+0.5 and O=L+0.5 L[1] (inherited); A10 changes only z=f;
A01 changes only O=L; A11 is their one interaction. Unit groups only, default off.
The same 18-term fit, recorded global state and integer-time application are used
in every arm. This pair is the smallest source-grounded convention change; its
two single-factor arms test whether an apparent gain depends on breaking the
linear-motion cancellation. All observations are fixed before scoring.

Prediction: A11 improves the ideal-known-observation/actual-global affine control
from 0.214314 Å RMS to approximately 0.085462 Å, but remains FAIL on actual native
observations (expected RMS >0.20 Å). Neither single-factor arm is a proposed fix.
With true linear global motion, A00 and A11 must both reproduce the ideal field
to 1e-11 px; the single-factor changes should break that property. This falsifies
"half-frame time alone is wrong" and tests a limited nonlinear-global interaction.

Required cases, fixed before launch: all five-frame identifiable retained CPU
fixtures zero/integer/fractional/affine/pedestal; noisy retained fixture as an
explicit STAR-observation sensitivity arm (its full-precision local observations
are unavailable). Flat/repeated remain UNIDENTIFIABLE, not acceptance cases.
Only affine has all 45 captured full-precision local observations. Integer and
fractional are model-zero/no-local paths, so all four arms are identical by source.
Zero/pedestal zero-state reconstructions will be distinguished from captured
full-precision native state; no hidden precision is invented.

N=5/9/13/20 controls: reproduce the existing reviewer periodic phase-ramp probes
at both recorded velocities, with five iterations/tolerance .5 and 50 iterations/
tolerance 1e-9. These have no local fit; all four arms must be identical. Carry
the N20 fractional isotropic-weight harmful row at five AND 50 iterations. Its
five-iteration 11.833 px error must remain, with zero intervention difference;
this is nonregression of a harmful control, not recovery or weight adoption.
Require agreement with every retained ndep.log RMS rounded to 0.001 px.

Score the complete global trajectory plus local field at all frames on the same
fixed ROI y[12:84], x[12:116], .885 Å/px. Runtime float64 and STAR-roundtrip fields
are separate. Retain RMS/p95/max limits .20/.40/.80 Å and report sampling status;
periodic long-trajectory probes are diagnostic, not new gate-role fixtures.
Serialize using the pinned metadata_table.cpp %.5f/%.6f and %.5e/%.6e rules,
validate that roundtrip against existing native STAR values first. Store complete
global trajectories and polynomial coefficients, sufficient to reconstruct every
field pixel. No generator, masking, ROI, gauge or limit will change after results.

Success needed to recommend a default-off C++ prototype: a previously failing
identifiable fixture must meet all three runtime AND STAR limits, with no
previous PASS lost and no harmful-control regression. Otherwise recommendation
is falsified; next discriminate the spatial content/window observation objective.
No further estimator attempts in this task.
