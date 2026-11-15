# Combined-build synthetic testing (#267 cases, #269 census, new image check)

## Evaluator integration, 2026-10-22

The repaired #267 checker (`66952415`) is integrated through #269
(`1b29b7f9`) by a normal merge. The historical results below and every file in
`evidence/` retain their original source identities and statuses. No native
campaign has been rerun or requalified at this integration head.

`eval_v2.py` now finds the source root above its own path, so the documented
command works from the committed location and helpers copied under a source
root remain usable. Each checker runs with a fresh private report path. Only
a report written by that invocation with exit 0 or 1 is consumed and saved as
`RUNDIR/CASE.checker.json`. An input-error exit 2 does not consume or replace
an older cached report: its row is `ABORT_NO_RESULT`, without image or sampling
status, while the independent field-only distance remains available for a
valid STAR. The wrapper's exit 0 means the batch was evaluated, not that its
native runs, field gates or checker results passed.

Finite estimates outside the fixed detector ROI now retain the checker field
metrics, `sampling_status=OUTSIDE_FIXED_ROI`, exit 1 and JSON null for
`image.estimated_motion_bilinear`. Other signal metrics remain present. The
fixed ROI, truth, field fallback and numerical gates are unchanged. Malformed
or nonfinite summed images remain input errors, not quality failures.

`OPENBLAS_NUM_THREADS=1 python3 tools/test_combined_eval.py -v` exercises the
actual wrapper and checker CLIs with small generated fixtures: source-path
discovery, copied helpers, ordinary reports, finite invalid sampling, nulls,
deterministic output, and cached success followed by malformed/nonfinite sums.
These are host contract controls, not estimator or scientific qualification.

## Historical combined-build results

**Result.** On one build containing all three candidate CUDA fixes (#254, #260, #270) plus the DC-oracle
hooks, both synthetic families behave as published, and the new image-level check sees the DC effect:

- **#269 census, 100 movies × {CPU, CUDA} × {DC none, DC both} = 400 native runs, all exit 0.**
  Field RMS reproduces #269's per-seed values to ≤ 4.9e-7 px (max over 410 matched arms; the difference is the
  6-significant-digit STAR rounding of the global shifts, see Provenance). #270 therefore does not change the field.
- **Image check, pedestal 32 (the only condition where DC conditioning matters):** field RMS
  1.788 → 0.299 px (CPU), 1.738 → 0.299 px (CUDA); in-band signal transfer 0.926 → 0.991 (CPU) and
  0.931 → 0.991 (CUDA), top band (0.12–0.16 cycles/px) 0.659 → 0.954 and 0.641 → 0.954.
  10/10 seeds improve on each backend for field and image (exact sign test p = 0.00195). CPU double CCF equals DC both.
  In every other condition DC none vs both is neutral/mixed for the image metrics (effect sizes ≤ 3e-4 in transfer).
- **#270 effect on images (CUDA, DC none, 100 movies, with vs without #270):** every change is in the outer 8 px.
  Beyond 8 px the sums differ by ≤ 1.9e-5 scene-σ (float noise from mean matching); 10/100 sums are byte-identical.
  In the 0–8 px band the median RMS change is 0.016 scene-σ, the largest single-pixel change 5.2 σ, and the change in
  squared error vs truth is better/worse/tie 53/37/10 (p = 0.113): no demonstrated improvement or harm at this noise level.
- **#267 eight cases:** CPU DC none is identical to main; DC both removes the pedestal error (2.39 → 0.36 px) but all gate
  cases still FAIL their field gate. `noisy` and `repeated` abort the unchanged checker (estimate leaves the fixed ROI) on
  both backends and both DC settings; that is a checker limitation, reported with independent field-only distances.
  CUDA DC none differs from main on several cases (below).

No production code is changed by this PR; nothing is merged. Shared CPU/CUDA bugs stay file-only.

## Sources and builds

| Build | Source | Use |
|---|---|---|
| `diag/combined-candidate` | `d044aaaa` = `diag/s1-dc-oracle` (`95e9d913`, #254+#260+`MC_DIAG_*` hooks) + #270 production change | all runs |
| `diag/combined-plain-control` | `6c11b8f5` = `31309df0` (#254+#260, no hooks) + #270 `b9440a09` | toggle-off control, #270 "with" arm |
| no-#270 plain | `31309df0` | #270 "without" arm |

The #270 merge touches only `src/acc/cuda/cuda_realspace_dw.cu` (+5/−2, identical to #270's file apart from the #254
lines). #270's CMake test registration conflicts with the diag branch and was left out. `31309df0` equals
#254+#260 in `src/` (checked by diff against both PR heads).
Release builds (`-O3 -DNDEBUG`, `BUILD_TESTING=OFF`), all exit 0: CPU on cpu64; CUDA sm_80 with real nvCOMP 5.3.0.16
(`USE_NVCOMP=ON`, unused for float MRC input) on 4GPUs. Binary hashes, build exits, GPU UUIDs in
`evidence/provenance-*.txt`. CUDA runs used UUID-selected A100s `GPU-063e5232…` and `GPU-b2cb2c39…`, one movie per
process under the per-GPU advisory locks, at most two held.

## Controls

**Toggle-off (byte identity).** All `MC_DIAG_*` unset, diag binary vs plain #254+#260+#270, MRC header[0:224]+payload
and STAR: one #269 movie (`pedestal32-s00`) and all 8 #267 cases, on CPU and CUDA: **all identical (0 differences)**.
`evidence/toggle-off-*-v2-compare.txt` plus the movie lines in `provenance-*.txt`. (The v2 section printed inside those
provenance files shows MISSING because of a wrong path in the first compare invocation; the `toggle-off-*` files are the
corrected compare.)

**Image check negative/positive controls** (seed 0 of every condition, 1536² interior crop, `evidence/controls/`;
SciPy cubic resampling of the raw movie, independent of production). Signal transfer by band
(0.01–0.04 / 0.04–0.08 / 0.08–0.12 / 0.12–0.16 cycles/px), dose 1:

| Sum | Transfer | FRC | in-band relRMSE |
|---|---|---|---:|
| truth vs truth | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 0 |
| oracle-aligned (true motion) | 1.005 / 1.004 / 0.983 / 0.977 | 0.917 / 0.831 / 0.474 / 0.123 | 1.094 |
| zero motion | 0.342 / −0.130 / 0.155 / −0.119 | 0.332 / −0.124 / 0.080 / −0.015 | 1.659 |
| wrong sign | −0.045 / 0.054 / 0.052 / −0.114 | −0.049 / 0.057 / 0.027 / −0.014 | 1.634 |

Zero-motion and wrong-sign sums score at ≈0 transfer; the oracle sum scores ≈1. `tools/test_realistic_image.py` runs
the same controls on a small noise-free movie and also checks that a border-only defect shows up only in the border bins.

## What the image check measures

`tools/check_realistic_image.py`. Truth is the generator's own continuous scene (`gen.scene`, cubic B-spline of the
oversampled field) sampled at detector pixel centres of frame 0 (the identity map), rendered once per geometry
(`truth-*.npy`, hashes equal on both hosts). The published non-DW sum `S` (`--save_noDW`, non-DW runs as in #269)
is normalised as `ŝ = (S/N − P)/(C·dose)` with no fitted gain. Interior metrics exclude a 128 px margin: Hann-windowed
Fourier rings in four bands, **signal transfer** `Re⟨Ŝ,T⟩/⟨T,T⟩`, FRC, and in-band relRMSE. The outer 64 px is reported in
real space (relRMSE by distance to the edge).

Limits: Poisson noise is not removed, so relRMSE is noise-dominated (≈1.08 at dose 1, ≈ the oracle's) and FRC is
bounded by SNR even for perfect alignment. Signal transfer is unbiased by independent noise and is the discriminating
number. At field errors of ~0.3 px the image metrics are indistinguishable from each other; they separate arms only
where the field is wrong by ≳1 px (pedestal 32 without DC; the out-of-model condition shows the polynomial-model limit,
top-band transfer 0.794 for every arm). Border metrics are real-space and noise-limited; the #270 pairing above is the
sensitive border test because noise cancels between two runs of the same movie.

## Per-condition results

Median over 10 seeds; full table (per band, FRC, relRMSE, border) in `evidence/tables.md`, per-seed rows in
`evidence/per_seed_arm.csv`. Transfer = in-band; `T top` = 0.12–0.16 cycles/px.

|Condition|Arm|Field RMS px|Transfer|T top|
|---|---|---:|---:|---:|
|dose 0.5|CPU none / both|0.42969 / 0.42998|0.9884 / 0.9884|0.943 / 0.943|
|dose 0.5|CUDA none / both|0.43045 / 0.42998|0.9885 / 0.9884|0.943 / 0.943|
|dose 1|CPU none / both|0.29920 / 0.29918|0.9911 / 0.9911|0.954 / 0.954|
|dose 1|CUDA none / both|0.29894 / 0.29918|0.9911 / 0.9911|0.954 / 0.954|
|dose 2|CPU none / both|0.19938 / 0.19996|0.9915 / 0.9915|0.954 / 0.954|
|dose 2|CUDA none / both|0.19951 / 0.19996|0.9914 / 0.9915|0.954 / 0.954|
|dose 4|CPU none / both|0.13369 / 0.13356|0.9921 / 0.9922|0.959 / 0.959|
|dose 4|CUDA none / both|0.13272 / 0.13356|0.9921 / 0.9922|0.959 / 0.959|
|out-of-model|CPU none / both|1.0425 / 1.0424|0.9614 / 0.9613|0.794 / 0.794|
|out-of-model|CUDA none / both|1.0423 / 1.0424|0.9613 / 0.9613|0.794 / 0.794|
|5760×4092|CPU none / both|0.24627 / 0.24611|0.9908 / 0.9907|0.937 / 0.937|
|5760×4092|CUDA none / both|0.2456 / 0.24611|0.9908 / 0.9907|0.937 / 0.937|
|pedestal 0|CPU none / both|0.29918 / 0.29918|0.9911 / 0.9911|0.954 / 0.954|
|pedestal 0|CUDA none / both|0.29918 / 0.29918|0.9911 / 0.9911|0.954 / 0.954|
|**pedestal 32**|CPU none / both|**1.78784 / 0.29918**|**0.9262 / 0.9911**|**0.659 / 0.954**|
|**pedestal 32**|CUDA none / both|**1.73834 / 0.29918**|**0.9307 / 0.9911**|**0.641 / 0.954**|
|pedestal 32|CPU double|0.29918|0.9911|0.954|
|amplitude ×0.25|CPU none / both|0.31416 / 0.29918|0.9908 / 0.9911|0.954 / 0.954|
|amplitude ×0.25|CUDA none / both|0.29715 / 0.29918|0.9909 / 0.9911|0.953 / 0.954|
|amplitude ×4|CPU none / both|0.29917 / 0.29918|0.9911 / 0.9911|0.954 / 0.954|
|amplitude ×4|CUDA none / both|0.29917 / 0.29918|0.9911 / 0.9911|0.954 / 0.954|

## Paired per-seed sign tests

Exact two-sided sign tests, ties |Δ| ≤ 1e-9; all four comparisons × four metrics × ten conditions are in
`evidence/paired_tests.csv` (multiplicity: 160 exploratory tests, p unadjusted). In the CSV the median Δ for transfer is
shown on the negated scale (negative = transfer increased).

- **DC none → both:** only pedestal 32 is significant on both backends, for field, transfer, relRMSE and border
  (10/0/0, p = 0.00195). Amplitude ×0.25 improves field on CPU (9/1/0, p = 0.0215; median −0.0101 px) but is neutral
  for image transfer (p = 0.34) and neutral on CUDA. One further nominal hit, out-of-model CUDA transfer (10/0/0,
  p = 0.00195), has an effect size of 2e-5, so it is not practically meaningful.
- **CPU vs CUDA:** with DC none, field is neutral in 9 of 10 conditions and nominally better on CUDA for amplitude ×0.25
  (9/1/0, p = 0.0215, −0.0116 px). With DC both, CPU and CUDA fields differ by ~1e-7 px; a few sign tests are
  nominally "significant" (for example nonsquare field, 1/9/0, p = 0.0215; dose 4 transfer, 0/10/0, p = 0.00195) at
  effect sizes of 1e-7 to 2e-7, which are numerically trivial and are not read as differences.

## #270 image effect

`evidence/effect270.json` (CUDA DC none, plain build with vs without #270, 100 movies; mean-matched, scene-σ units).

|Distance to edge px|median RMS change|max change|Δ squared error: better/worse/tie|sign p|
|---|---:|---:|---|---:|
|0–8|0.0164|5.16|53/37/10|0.113|
|8–16|6.6e-9|9.5e-6|42/45/13|0.83|
|16–32|7.9e-9|4.8e-6|46/41/13|0.67|
|32–64|8.0e-9|9.5e-6|51/38/11|0.20|
|64–128|8.3e-9|9.5e-6|47/42/11|0.67|
|≥128|1.1e-8|1.9e-5|44/46/10|0.92|

## #267 eight cases (field RMS px, 128×96×5; original-checker status)

Main values are #269's published native runs at `36913740`. Combined DC none on CPU is identical to main; CUDA DC none
changes because #254/#260/#270 are in the build.

|Backend|Case|main|combined DC none|combined DC both|
|---|---|---|---|---|
|CPU|zero|0.0000 PASS|0.0000 PASS|0.0000 PASS|
|CPU|integer|0.2979 FAIL|0.2979 FAIL|0.5865 FAIL|
|CPU|fractional|0.5922 FAIL|0.5922 FAIL|0.3689 FAIL|
|CPU|affine|0.4547 FAIL|0.4547 FAIL|0.3616 FAIL|
|CPU|pedestal|2.3945 FAIL|2.3945 FAIL|0.3614 FAIL|
|CPU|noisy|2.6474 ROI error|2.6474 abort|1.8852 abort|
|CPU|flat|2.3779 UNID.|2.3779 UNID.|2.3779 UNID.|
|CPU|repeated|18.6823 ROI error|18.6823 abort|10.1837 abort|
|CUDA|zero|0.0000 PASS|0.0000 PASS|0.0000 PASS|
|CUDA|integer|0.5148 FAIL|0.2850 FAIL|0.4525 FAIL|
|CUDA|fractional|0.3391 FAIL|0.3794 FAIL|0.3689 FAIL|
|CUDA|affine|0.3488 FAIL|0.3231 FAIL|0.3616 FAIL|
|CUDA|pedestal|2.3945 FAIL|2.3945 FAIL|0.3618 FAIL|
|CUDA|noisy|1.6921 FAIL|2.9784 abort|1.8852 abort|
|CUDA|flat|2.3779 UNID.|2.3779 UNID.|2.3779 UNID.|
|CUDA|repeated|67.5690 ROI error|68.6746 abort|43.3685 abort|

"abort" = the unchanged #267 checker exits 2 (`candidate samples outside fixed valid detector region`). This is a
checker limitation (reported on #267, not fixed here). Field RMS is from `eval_v2.py`, an independent field-only
distance with the same ROI, truth and STAR field; no ROI or tolerance was relaxed. The CUDA `noisy` case moved from a
checker FAIL on main to an abort on the combined build because its estimate now leaves the ROI. The #267 cases are 5-frame
128×96 movies with 3×3 patches at most; their small changes between builds are not a population result.

## Reproduction

```sh
# builds (per host), then the census with the extended runner (defaults reproduce the 900-arm census)
python3 tools/run_realistic_motion_census.py --root ROOT --binary BIN --backend {cpu,cuda} --cpus 8-15 \
  --results results-comb --dc-arms none both [--double-conditions pedestal32]
python3 docs/post_rc0/s1/synth_combined/eval_field.py ROOT results-comb 8       # field metrics
python3 docs/post_rc0/s1/synth_combined/image_batch.py eval ROOT results-comb x 8
python3 docs/post_rc0/s1/synth_combined/image_batch.py controls ROOT dose1-s00 controls.json
python3 docs/post_rc0/s1/synth_combined/image_batch.py effect ROOT results-no270 results-plain270 effect270.json
python3 docs/post_rc0/s1/synth_combined/run_v2_cases.py ROOT NAME {cpu,cuda} BIN {none,both,unset} CPUS [UUID]
python3 docs/post_rc0/s1/synth_combined/eval_v2.py FIXTURES RUNDIR OUT.json
python3 docs/post_rc0/s1/synth_combined/analyze.py DATA OUT; python3 .../analyze_extra.py DATA OUT
OPENBLAS_NUM_THREADS=1 python3 tools/test_realistic_image.py -v
```

Movies are #269's fixtures (hash-checked against their receipts on every run; copies on cpu64 were verified by SHA-256 and
deleted after use, originals untouched). #267 fixtures were regenerated with the PR generator and are byte-identical to
#269's. `cpu_orchestrator.py`, `push_fixtures*.sh` stream fixtures between hosts under a disk cap.

## Provenance and deviations

- **Runtime model capture.** #269's census used the JSON capture overlay on `97fd8107`. The diag head here writes the
  polynomial coefficients as text without the global shifts, so `eval_field.py` takes the coefficients from that file and the
  global shifts from the STAR table (6 significant digits). This is why field RMS differs from #269 by up to 4.9e-7 px rather
  than bit-equally; the comparison is in `evidence/tables.md`.
- **CPU build** is CPU-only (as in #269); CUDA runs use `--ingest float`, and nvCOMP is built in but not exercised.
- **Runner change.** `tools/run_realistic_motion_census.py` gained optional `--dc-arms`, `--double-conditions`, `--results`
  and `--conditions`; defaults are unchanged. CI runs the new image test.
- CPU workers: eight pinned CPUs each on cpu64 (cores 8–39); CUDA: eight pinned CPUs per worker. Timing was not measured.
- Not done: the image check was not run on DC global-only/local-only arms, and CPU double was run only on pedestal 32.
  No claim is made about CTF/FSC/downstream science or performance.
