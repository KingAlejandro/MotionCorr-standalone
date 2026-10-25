# E1 prediction, frozen before characterization

Parent cd4c996bdcffc0e7080aa8f817a11c5e449fe5c8; numerical source remains
805d9de27898b4a10e6212e65098d5995a40fdb1. No native MotionCorr/CUDA runs.

The N5 production-weight 50-iteration errors are .391948/.392553 px
(.346874/.347409 Å), not .347 px. These are periodic phase-ramp controls;
the separate retained native fixture errors are .263614/.524057 Å.

Prediction: the N5 inherited separable-parabola simultaneous sum-of-others map
has an unstable truth stationary point and attracts a nonzero oscillation,
rather than a second stationary field. Expect a period-two endpoint with
nonzero update after 500 iterations. The pinned linearized eigenvalue near
-1.196 motivates this prediction. A truth start has a near-zero first update,
but finite precision can eventually perturb it away; stationarity is not
stability. No assumption that a truth start stays there for 500 floating-point
updates is made. The real integer/fractional stored frames may have small
nonperiodic/sample effects and distinct basins; report what happens.

Characterize four inputs: phase vel0/vel1 N5, retained integer/fractional
five-frame movies. For each, use a 3x3 grid of starts s_x=alpha_x*truth_x,
s_y=alpha_y*truth_y, alpha in {0,.5,1}. This includes zero and truth.
Always run 500 updates; do not let a first tiny update stop the characterization.
Retain raw/applied update-norm and truth-error histories, states at 50 and 500,
last nine states and lag-p distances p=1..8. Measure a fresh map update at each
endpoint. Numerically differentiate the anchored map at truth with +/- .001 px
perturbations. Record eigenvalues, not only a routing label.

Diagnostic labels, not truth gates: fixed point if endpoint update <1e-7 px;
period p if endpoint update is larger and lag-p distance <1e-6 px; otherwise
report slow/irregular convergence or unresolved dynamics. No tolerance tuning.
The existing double-map baseline must reproduce W5 phase trajectories and the
pinned independent W4 fixture trajectories within 1e-5 px before new evidence
is credited. Native float32 results remain a separate comparison axis.

After characterizing, freeze ONE intervention selected from that evidence in
E1-INTERVENTION-PREDICTION.md before evaluating it. A minimal candidate if the
predicted oscillation is confirmed is half-gain state updates, retaining the
same unscaled candidate norm for stopping. This is a provisional choice, not
an executed arm. A wrong stationary point/basin would instead require a
different frozen choice. Do not run both candidates.

CPU64 CPUs48-55 only, nonblocking /tmp/motioncorr-w5-cpu48-55.lock, one BLAS/OMP
thread; reuse the owned W5 scratch with a fresh round2 subdirectory. Scratch
remains <10 GB. Scientific histories are retained even if a control fails.
