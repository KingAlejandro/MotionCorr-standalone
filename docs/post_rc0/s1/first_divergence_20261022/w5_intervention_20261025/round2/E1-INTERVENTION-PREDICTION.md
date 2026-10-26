# E1 intervention prediction, after characterization and before execution

All four five-iteration baseline trajectories reproduce the pinned W4/W5
double-map results exactly. N5 zero-start endpoints after 500 updates have
fresh update RMS .435449/.739949 px (phase vel0/vel1), .613469/.390646 px
(retained integer/fractional). No lag period <=8 is certified. The strict
period-two prediction failed; this is persistent oscillatory nonconvergence,
not evidence of a second fixed point or ordinary monotone slow convergence.
Both ideal phase-ramp truth starts stay exactly at truth for 500 updates.
Stored fixture truth starts are perturbed by 1.63e-8/3.77e-7 px on the first
step and depart. The map at truth has eigenvalues approximately .698524 and
-1.192520. The 3x3 start grid finds no ordinary attraction basin to truth.

Chosen ONE estimator change: under-relax the anchored GLOBAL state update by
gain .5. Re-shift the spectra by the same scaled update. Preserve the original
unscaled candidate RMS in the convergence test; otherwise halving the step
would silently loosen the .5 px stop. Patch alignment, peak estimator, weight,
window, convention and 18-term fit are unchanged. No alternative initializer,
all-pairs solve or peak modification will also be tested.

Prediction: the local eigenvalues become .849262 and -.096260, so the
50-iteration arm should recover the retained integer/fractional fixtures to
all .20/.40/.80 Å limits in runtime and STAR, although it need not meet the
very strict 1e-9 update stop by iteration 50. Five-iteration/.5 px stopping may
leave substantial error; report that separately and do not change its limit.
This is evidence for a default-off research prototype only if a previously
failing identifiable fixture passes and no mandatory harmful control worsens.

Evaluate baseline gain1 and candidate gain.5 on all eight retained CPU fixture
inputs, with both stop rules (5/.5 and 50/1e-9). Run double-map and float32-map
replay as separate arithmetic axes. The latter rounds the unnormalised CCF map
to float32, but still uses NumPy double Fourier arithmetic; it is NOT native
CPU reproduction or a CUDA claim. Validate the unchanged peak rule against all
captured float32 patch maps/candidates first, to 1e-6 px. Preserve source patch
acceptance, including null models for too few accepted observations. Flat and
repeated remain UNIDENTIFIABLE. Noisy is characterization, not new acceptance.

Also score both velocities and N5/9/13/20, both weights, both stop rules using
the existing double phase-ramp controls. Require baseline trajectories to
match W5 within 1e-5 px, including the N20 11.832823 px harmful case. Harmful
nonregression means candidate five-iteration RMS <= baseline+1e-6 px, with
runtime and STAR field scores visible; failure blocks a prototype recommendation.
Do not retune gain if it fails. Retain every update and full final trajectory.

For N>=9, report the ordered 5-stop minus 50-stop trajectory/field term in Å,
and errors against truth for each endpoint. These are path-dependent measured
stopping terms, not independent errors to sum and not stopping-rule adoption.
Preserve the fixed ROI, gauge, .885 Å/px and all original limits. No model floor
subtraction. No native or CUDA execution; the existing native .26/.52 Å fixture
records are comparators, not the new double/float-map baseline.
