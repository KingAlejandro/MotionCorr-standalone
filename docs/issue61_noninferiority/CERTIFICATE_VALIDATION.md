# PR65 certificate validation, 2026-10-22

This is a host-only validation fix based on PR65 head
`45f07f143122db9baa7574da7c9c60ac6156517a`. It does not amend the frozen protocol,
historical evidence, margins, harm models or numerical gates. Stage B remains
**INCONCLUSIVE**. The live issue61 discussion and PR65 review disposition were read
before implementation; the PR body's superseded PASS headline remains the parent's task.

The pinned analyser was exercised as a subprocess on synthetic post-processing STARs
before changing it. `coverage_demonstration="yes"` and `{"n":20,"false_pass":20}` both
restored real-arm PASS. So did asserted baseline hashes that disagreed with local files.
A `ctrl_envelope_b20` certificate with target rho 1 and measured rho .90 certified,
and supplying target .90 overrode the historical target. These are implementation
counterexamples, not scientific control experiments.

## Boundary enforced

The consumer checks certificate object/list structure, numeric margin, unique `ctrl_`
names and finite, ordered available point/interval values. These are structural checks,
not an operating-characteristic acceptance schema. Missing bounds can remain descriptive.
It requires `bit_identical` to be the Boolean true **and recomputes** SHA-256 over
bytes 1024+ of both local `rec/cpu/held22_half*_class001_unfil.mrc` files. Both certificate
digest sets must match both recomputed values. Missing files, empty payloads or digest
mismatches refuse the certificate. This retains the historical digest convention;
it is not a new general MRC validator. Header labels are excluded as before.

Matching digests admit **identity-bound descriptive entries only** (`certificate.used`);
`scientific_certification_accepted` remains false. Hash agreement does not authenticate
remote provenance, the control estimates, matched settings, or scientific equivalence.
The JSON is loaded once; coverage is not reread from a potentially changed file.

Certificate-supplied `designed_rho` is retained under an explicitly unvalidated field
and cannot override the historical reference target. Historical noise targets are
unvalidated estimates from a contradicted/fitted model; they do not establish truth.
Neither measured rho nor those targets establish independent harm. Local controls follow
the same rule. Measured rejection and its observed boundary remain available as unvalidated
description, separately from validated S2 certification. S1 remains UNTESTED.

Coverage assertions are retained as unvalidated description when identity binding succeeds.
There is deliberately no positive certification path until an accepted independent forward
harm model and a maintainer-approved coverage/operating-characteristic policy are implemented.
Every computed real-arm Stage B verdict is forced to INCONCLUSIVE with explicit reasons;
its original numerical decision is retained as `verdict_before_validity_gate`.

## Focused verification

Run from the isolated PR65 worktree, using the explicit interpreter:

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1
PY=/Users/alex.konstantinov/.local/bin/python3
git show 45f07f143122db9baa7574da7c9c60ac6156517a:docs/issue61_noninferiority/scripts/i61_analyse_B.py > /tmp/pr65-analyser-pinned-45f07f14.py
$PY docs/issue61_noninferiority/scripts/i61_certificate_host_controls.py --analyser /tmp/pr65-analyser-pinned-45f07f14.py --expect-legacy-holes --out /tmp/pr65-certificate-baseline-final-20261022.json
$PY docs/issue61_noninferiority/scripts/i61_certificate_host_controls.py --baseline /tmp/pr65-certificate-baseline-final-20261022.json --out /tmp/pr65-certificate-regression-final-20261022.json
git diff --check
```

Output reports use exclusive creation: choose new names for subsequent runs. Fixture STARs,
tiny MRCs and analyser JSONs use disposable scratch, never the retained result filenames.
The script invokes the actual analyser, including its parser, estimators and publication step.
It exercises both forged coverage values, digest mismatches (each certificate side and each
local payload binding), missing/empty maps, label-only changes, malformed certificates,
measured-only harm, design override and absent certificate. The positive identity control
checks that valid binding remains usable for description while certification stays closed.

Recorded result: **PASS**, 7 pinned-analyser subprocesses and 20 fixed-analyser subprocesses.
Independent source review found one fixture alias: both certificate hash sets originally
referenced the same dictionary, so a one-sided mutation changed both sides. The fixtures now
use independent dictionaries and require the untargeted side to remain unchanged and the
rejection reason to name the targeted side. The 7/20 subprocess controls pass again. Two
temporary analyser mutants, each omitting one side's local digest comparison, are both
rejected by the corrected controls. The analyser itself is unchanged by this review repair.
All synthetic descriptive results, including nonzero jackknife SEs and bounds, compare exactly
before/after (digest `33b5b7d10ffefd46a13592a91ac67931fce3a1b225e78c1d7c59bd58674bd529`).
Full-sample B1/B2/B3 values for both real arms and both analysis sets, and CPU/real-arm point
estimates, also reproduce exactly from the retained `fsc_curves.json` export against
`stageB_reconstruction.json`. That replay uses synthetic jackknives: historical raw-map and
historical interval reanalysis are **UNRUN**. No reconstruction, remote compute, native GPU,
performance or new scientific qualification was attempted.

Environment: macOS arm64, Python 3.13.7, NumPy 2.4.2, SciPy 1.17.1; sequential subprocesses,
all listed numeric thread controls set to one. Occupancy was checked with
`ps -Ao pid,pcpu,comm`, `uptime` and `df -h .`: the host had unrelated busy browser/security
and Refmac processes (load 19.16/15.58/14.65), with 35 GiB available. Those were left alone;
this is a correctness check, not a timing comparison. No new dependencies were added.

## Decisions left open

Maintainers still need to accept an independent forward harm definition (including whether
any proposed thinning construction supplies exact truth), prospective severities and
replication/precision regimes, and an operating-characteristic validation/acceptance policy.
No sample count, false-pass threshold, margin, harm model, noise truth or thinning truth is
chosen by this patch. A future certification implementation needs separate prospective design
and validation; a truthy JSON value cannot enable it.
