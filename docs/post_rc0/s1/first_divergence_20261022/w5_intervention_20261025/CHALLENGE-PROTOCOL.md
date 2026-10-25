# W5 challenge protocol, before execution

Source 805d9de27898b4a10e6212e65098d5995a40fdb1; retained packet head
7b76b848650726c018567312b6526269af72496f. Inputs are frozen by INPUTS.json
757558777b1e89611fa10f0a61dbcd941920207440c419fd1826ece86d07adb5.

On all nine SAME captured iteration-1 CPU spectra, align every frame by its
known material-centre residual (known field minus retained global). Correlate
frame i with the TRUTH-aligned sum of others. Report both the absolute oracle
trajectory (anchored to frame zero) and the update when initialized at truth.
A nonzero anchored update and positive AC-objective gain refute stationary truth;
zero updates with a different zero-start fixed point support an iteration/basin
explanation. Restart the continuous iteration at truth and compare its endpoint
with W4's reproduced zero-start endpoint. These are local Newton stationary
points, with no claim of certified global maximization.

Controls: inherited fit must close within 1e-11 px against the full-precision
runtime field; same-input W4 fixed points within 1e-6 px; phase-ramp translations
of the identical captured frame-zero spectrum must have truth updates below
1e-8 px. The derivative diagnostic removes the constant DC in double only to
measure tiny objective gains accurately; it does not change the estimator.
Report derivative/Hessian/gain and every patch, including equivariance checks.
Compare ideal known observations through inherited and integer-time conventions,
with actual and true global trajectories, on the unchanged ROI and gates.

No intervention selected or executed yet. No native run. Part 1 uses cpu64 under
flock -n /tmp/motioncorr-w5-cpu48-55.lock, taskset -c 48-55, all library thread
counts one. Namespace /tmp/motioncorr-w5-20261025-7b76b848, <10 GB.

Preparation correction: the first staging command stopped while exporting a
nonexistent src/motion_model.cpp. It executed no numerical calculation. The
source file is src/micrograph_model.cpp; staging then completed. Original inputs
were read-only throughout.
