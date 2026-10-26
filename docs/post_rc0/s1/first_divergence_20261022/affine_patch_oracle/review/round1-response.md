# Author response to independent review R1

Review of `07773483`. All four findings are accepted as claim-precision or wording
issues and applied to `README.md` only (new section "Corrections after review R1"
plus the in-place edits listed below). No number, label, gate, script, protocol,
retained attempt or historical total changed (2 PASS / 10 FAIL / 4 UNIDENTIFIABLE);
nothing was recomputed and no SSH, native, GPU or build step was run. The
reviewer's report is unchanged in `round1/`.

| ID | Finding | Verification by the author | Response |
|---|---|---|---|
| F1 | Frame-0 "anchor effect" is an exact float32 tie broken by different tie rules, amplified by the parabola cross-term; README framed it as a value gap | Confirmed from retained `attempt02.json`: `exact_ties = 2` for frame 0 iteration 1 in both backends (winners CPU `(-1,0)`, CUDA `(0,0)`); CUDA also has ties at frame 0 iterations 2–5 (3, 2, 2, 3) and frame 1 iteration 3. The 0.49/0.53 ULP gaps are the double-precision gaps. Max float-versus-double map difference at iteration 1: 2.31 (CPU), 2.35 (CUDA) ULP. The +0.49 px cross-term and −0.05 y / −0.09 x rounding split are the reviewer's numbers from a control the author did not rerun (the double-map parabola at `(-1,0)` is not in the retained output); they are attributed as such | README paragraph rewritten; table row relabelled "native candidate − parabola on the double map (CPU frame 0: different lattice point)"; ULP-versus-curvature explanation added |
| F2 | N-C mutants change only the comparand or the render, none mutates the estimator; the 11 467–72 114× separations belong to N-E only | Confirmed from the script (N-C1..N-C3 alter the expected value; N-C4 renders the opposite sign) and from the separations in `attempt02.json`, which exist for N-E only | Pre-registered table row split into geometry and comparator/render mutants; estimator witnesses stated as G-N (≤ 2e-8 px) and the ≤ 2.4 ULP map agreement; reviewer's G-E power measurement quoted and attributed. The frozen `protocol.json` keeps its N-C naming, unchanged |
| F3 | CPU/CUDA accept/exclude difference is confounded with different global states; no matched-input cross arm | Confirmed: CPU frame 4 state `(-2.886, 1.754)`, CUDA `(-3.448, 2.450)` (both in the hash-bound `state/global.txt`); no arm applies one backend's arithmetic or tie rule to the other's input | Bullet retitled "the cause is not isolated"; statement limited to each backend's own sensitivity to float32 and ties |
| F4 | G-CS is self-consistency; the native sign witness is the native-input-versus-render agreement plus G-E; "Input is not the problem" over-broad | Confirmed from the script (G-CS compares the oracle's render with its own `inv`) | Bullet retitled "at iteration 1, for the fixed-template objective", later iterations and the sum-of-others objective stated as untested; G-CS limit added to the corrections section |

Open items kept: one patch of nine, fit UNRUN, no accuracy fix or acceptance, the
window share not separated into crop/weight/content periodicity, and the 16-process
capture proposal in `future_native_capture_manifest.json` stays a HELD, unlaunched
proposal (parent decision).
