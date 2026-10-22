# Independent review round 1: response matrix

Review of `7d85898d` by an independent Opus reviewer, 2026-10-22. The reviewer's
report, scripts and outputs are preserved byte-identical in `round1/`
(`round1-artifacts.json` binds them; the four files listed in the reviewer's
`hashes.txt` verify). The author verified each finding against the source,
retained records or the reviewer's recorded outputs, without rerunning the
reviewer's scripts and without any new native process. Responses change
documentation and the machine ledger only. Raw arrays, native receipts, the
frozen campaign manifest, the native evaluation and the NOT MET outcome are
unchanged. The pre-review `ledger.json` remains at `7d85898d`.

| ID | Finding | Verification | Response |
|---|---|---|---|
| F1 | #264 exclusion for pedestal relied on "model 0, 1×1 patch"; pedestal ran model 1 with 9 patches | Confirmed: #273 argv uses `--patch_x 3` for pedestal; log shows 9 patches, all RMSD 0, fit RMSD 0; STAR has 36 coefficients printed 0.000000; no guard decision is logged | Accepted. Exclusion now applies only to integer/fractional/flat/repeated. For pedestal, a zero polynomial cannot exceed either guard domain, so #264 is unlikely to change it, but this is an inference; runtime coefficients were not captured, so #265 is likewise not excluded by proof |
| F2 | Weight checked only against the inherited formula; "earliest" holds only relative to that objective; source specifies quadratic interpolation; isotropic weight with the unchanged parabola passes | Confirmed: the weight row compares float to the inherited formula; `motioncorr_runner.cpp` comments "Quadratic interpolation by Jasenko"; reviewer `indep.json` isotropic 5-iteration replay 0.043 px integer, 0.049 px fractional | Accepted. The diagnosis is stated relative to the inherited objective; the estimator departs from the maximum of the objective it estimates, not from its specification; weight shape and estimator are co-causes, either change alone passes these two fixtures offline; no single exclusive cause is claimed |
| F3 | "Not the stopping rule" holds only for N = 5 | Confirmed from `ndep.log`: production weight + parabola, 50 iterations, reaches 0.044 / 0.002 / 0.000 px (integer) and 0.067 / 0.001 / 0.000 px (fractional) at N = 9 / 13 / 20, while 5 iterations at tolerance 0.5 fail (0.27–0.48 px). These are reviewer synthetic phase-ramp probes, not fixtures | Accepted. Nonconvergence is bounded to the 5-frame fixtures; at other frame counts the 5-iteration / 0.5 px stop can be a co-cause. Added to Result, Interpretation, Limits and the held questions |
| F4 | README called 0.2–0.45 px the "frozen" band | Confirmed: frozen manifest (`daaa2217`) says "roughly 0.26–0.34 px"; the 0.2–0.45 px test is in `analyze_native.py` from `98855b28` (committer time 19:16:41 UTC, before the 19:20:31 UTC launch; self-reported) | Accepted. Both bands and their sources are stated; fixedref-cuda-fractional (0.495 px) is NOT MET under both, fixedref-cpu-fractional (0.308 px) is inside both. Original manifest and evaluation records are not rewritten |
| F5 | Pedestal single-value map stated as fact | Confirmed: offline float32 rounding of a double map from regenerated fixtures, plus native zero trajectories and logs; no native map | Accepted. Marked inferred in Result, ledger table and `ledger.json` |
| F6 | "Biased on anisotropic peaks" is imprecise | Confirmed by the packet's own cross-term check (0.0026 px) and reviewer Hessians | Accepted. The bias requires a nonzero cross term (correlated, rotated peak); axis-aligned anisotropy alone gives none; the error comes from slicing through the integer winner |
| F7 | Same-state row compares to the exact continuous maximum, not an exact-objective parabola | **Disagree.** `offline_stages.py` computes `native_minus_exact_parabola_px = |native − parabola(double map)|`. Frame 1 iteration 1 (CPU): native (1.667, −3.25), parabola on the double map (0.898, −2.302), difference 1.221 px; the continuous maximum (1.444, −2.719) would differ by 0.576 px | Label clarified to "same parabola rule on the double-precision map of the same state". Value unchanged; the continuous maximum is reported separately in `offline/attempt03.json` |
| F8 | Isotropic weight is not a safe fix | Confirmed from `ndep.log`: N = 20 fractional, isotropic weight, 5 iterations, 11.833 px; production weight 0.279 px | Accepted. Recorded as counter-evidence; no fix, default or adoption recommendation is made |

Held-issue recommendation (not filed by the author): two separate,
cross-linked HELD/file-only questions, both RELION-inherited:

1. B-factor weight x-normalization (`nx/2+1` vs `nx`) in global and patch
   alignment, internally inconsistent with dose weighting's `nx²`. A change has
   its own failure mode (F8).
2. Separable 3-point peak estimate on correlated peaks, its interaction with
   the sum-of-others gain N/(N−1), and the 5-iteration / 0.5 px stop (F3).
