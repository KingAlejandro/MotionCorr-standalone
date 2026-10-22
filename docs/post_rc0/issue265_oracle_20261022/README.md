<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# #265 native round-trip oracle (preparation only)

Result: on the constructed fixtures the real `ThirdOrderPolynomialModel::write` then `::read` changes coefficients and
shift fields, and the same fixtures round-trip with zero error when the coefficient text is written at `%.17g`.
This is a prerequisite oracle. It is not a production fix, not an accuracy claim about any movie, and not a performance or
science result. #265 stays FILED ONLY pending the maintainer's parity decision. Source is unchanged.

## What was run

- Source: `3691374061f782bc84531fd1c79d017ddcb5a7c2` (main), clean (`receipts/iteration2/source_dirty.txt` empty). The
  harness is not part of the CMake build and no `src/`, tests or CMake file was touched.
- Library: `motioncorr_core` built with the project's own CMake (Release, `-DCUDA=OFF -DBUILD_TESTING=OFF`, `-j1`, exit 0).
  Harness flags, defines, includes and link line are copied from that build's `flags.make` / `link.txt` (`receipts/iteration2/build_options.txt`).
- Toolchain: macOS 27.0 SDK, Apple clang 21.0.0, arm64 (Apple M4 Pro), libc++. Not the project's qualified Linux x86-64 GCC.
  Single thread, `OMP_NUM_THREADS=1`.
- Harness: `harness/roundtrip_oracle.cpp` calls the real `getShiftAt`, `write`, `read` (and through them the real `MetaDataTable`
  formatter and parser). It writes to a file with the real `write`, reads it with the real `read`, and compares against the
  never-rounded in-memory doubles. Nothing from the formatter or parser is ported.
- Inputs: `fixtures.txt` (11 constructed fixtures, 36 coefficients each, two geometries 3838x3710 and 5760x4092, 26 pixel positions each,
  frames 0-49; 2600 samples per fixture per route). The table and the criteria in `PRE_RUN_CRITERIA.txt` were frozen before any run
  (`FROZEN_BEFORE_RUN.txt`). Run with `run.sh <src> <build> <out>`.
- Hashes (`receipts/iteration2/hashes.txt`): harness binary `d1ccb52a…5ea5636`, `libmotioncorr_core.a` `2c237ae5…d07f4`,
  harness source `5e69f974…f0235`, `fixtures.txt` `ef11984e…2bb2d`. Full per-sample CSV (9.7 MB, 54,600 rows plus header; F09 full-precision produced none, hash in
  `samples_full.csv.sha256`) is not committed; rerunning reproduces it.
- Exit codes: library build 0, harness build 0, harness run 0. Stderr of the run holds the real reader's error for F09 (below).

## Results (measured; no tolerance or gate applied)

Route `real-write-read` is the real serializer. Route `fullprecision-test-only` is a TEST-ONLY control: the real written text with
only the coefficient token replaced by the `%.17g` rendering of the pre-write double, read by the real `read`. It detects and removes
the formatting error; it implements nothing. Shift errors are post minus pre, unbinned px, from the same compiled `getShiftAt`.
Ranges are 0-indexed frames: early 0-5, mid 6-17, late24 18-23, gap 24-33, late40 34-39, gap2 40-43, late50 44-49.

| fixture | route | coeffs not bit-equal | max coeff abs err | max vec early (px) | max vec mid (px) | max vec late24 (px) | max vec gap (px) | max vec late40 (px) | max vec gap2 (px) | max vec late50 (px) | max vec all (px) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F00_zero | real-write-read | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F00_zero | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F01_exact | real-write-read | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F01_exact | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F02_ordinary | real-write-read | 36 | 4.815e-06 | 1.347e-04 | 1.608e-03 | 2.954e-03 | 6.101e-03 | 8.531e-03 | 1.038e-02 | 1.348e-02 | 1.348e-02 |
| F02_ordinary | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F03_neg_z3_const | real-write-read | 1 | 2.713e-06 | 3.391e-04 | 1.333e-02 | 3.301e-02 | 9.749e-02 | 1.609e-01 | 2.157e-01 | 3.192e-01 | 3.192e-01 |
| F03_neg_z3_const | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F04_neg_z3_xy | real-write-read | 1 | 2.713e-06 | 8.478e-05 | 3.332e-03 | 8.252e-03 | 2.437e-02 | 4.023e-02 | 5.392e-02 | 7.979e-02 | 7.979e-02 |
| F04_neg_z3_xy | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F05_pos_near_switches | real-write-read | 22 | 5.000e-07 | 5.101e-05 | 1.939e-03 | 4.793e-03 | 1.414e-02 | 2.332e-02 | 3.125e-02 | 4.623e-02 | 4.623e-02 |
| F05_pos_near_switches | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F06_neg_near_switches | real-write-read | 22 | 4.568e-06 | 1.616e-04 | 5.488e-03 | 1.347e-02 | 3.948e-02 | 6.501e-02 | 8.702e-02 | 1.286e-01 | 1.286e-01 |
| F06_neg_near_switches | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F07_late_frame_z3_stress | real-write-read | 36 | 4.568e-06 | 4.758e-04 | 1.526e-02 | 3.691e-02 | 1.068e-01 | 1.751e-01 | 2.338e-01 | 3.445e-01 | 3.445e-01 |
| F07_late_frame_z3_stress | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F08_width_edges | real-write-read | 5 | 5.000e-01 | 1.027e+00 | 1.584e+01 | 3.660e+01 | 1.033e+02 | 1.685e+02 | 2.245e+02 | 3.302e+02 | 3.302e+02 |
| F08_width_edges | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| F09_tiny_and_signed_zero | real-write-read | 3 | 1.000e-30 | 1.382e-29 | 4.745e-29 | 9.513e-29 | 7.195e-28 | 1.449e-27 | 2.122e-27 | 3.461e-27 | 3.461e-27 |
| F09_tiny_and_signed_zero | fullprecision-test-only | READ FAILED | |  |  |  |  |  |  |  |  |
| F10_neg_z3_all_corners | real-write-read | 4 | 2.713e-06 | 5.995e-04 | 2.356e-02 | 5.835e-02 | 1.723e-01 | 2.845e-01 | 3.813e-01 | 5.642e-01 | 5.642e-01 |
| F10_neg_z3_all_corners | fullprecision-test-only | 0 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |

Worst sample per real-write-read fixture (by vector error):
| fixture | geometry | frame | px | py | pre (x,y) | post (x,y) | err (x,y) | vec |
|---|---|---|---|---|---|---|---|---|
| F02_ordinary | G2 | 49 | 5759 | 0 | (16.9229, -10.1871) | (16.9094, -10.187) | (-1.348e-02, 1.123e-04) | 1.348e-02 |
| F03_neg_z3_const | G1 | 49 | 0 | 0 | (-143.851, 0) | (-143.532, 0) | (3.192e-01, 0.000e+00) | 3.192e-01 |
| F04_neg_z3_xy | G1 | 49 | 0 | 0 | (0, -35.9627) | (0, -35.8829) | (0.000e+00, 7.979e-02) | 7.979e-02 |
| F05_pos_near_switches | G2 | 49 | 5759 | 4091 | (1.20298e+08, 4670.26) | (1.20298e+08, 4670.29) | (3.572e-02, 2.935e-02) | 4.623e-02 |
| F06_neg_near_switches | G2 | 49 | 0 | 4091 | (-1.20297e+08, 4212.8) | (-1.20297e+08, 4212.84) | (-1.239e-01, 3.439e-02) | 1.286e-01 |
| F07_late_frame_z3_stress | G2 | 49 | 5759 | 4091 | (-189.716, -131.522) | (-189.386, -131.619) | (3.302e-01, -9.799e-02) | 3.445e-01 |
| F08_width_edges | G1 | 49 | 0 | 0 | (3.63727e+09, 0) | (3.63727e+09, 0) | (3.302e+02, 0.000e+00) | 3.302e+02 |
| F09_tiny_and_signed_zero | G1 | 49 | 0 | 0 | (-2.352e-297, 0) | (3.46063e-27, 0) | (3.461e-27, 0.000e+00) | 3.461e-27 |
| F10_neg_z3_all_corners | G1 | 49 | 0 | 0 | (-179.814, -179.814) | (-179.415, -179.415) | (3.990e-01, 3.990e-01) | 5.642e-01 |

Controls against the criteria declared beforehand:

- K1 (zero and exactly representable fixtures, real route): met. F00 and F01 read back bit-identical, error exactly 0.
- K2 (full-precision file, every fixture): met for 10 of 11. F09 failed: the real reader throws
  `Invalid floating-point STAR value: 4.9406564584124654e-324`. The follow-up table `fixtures_followup_subnormal.txt`
  (written after seeing this, results in `receipts/followup_subnormal/`) shows the smallest normal double and 1e-300 round-trip bit-exactly
  while subnormals (`1e-310`, `4.94e-324`) are rejected by this reader. This is the libc++ `istream >> double` underflow behaviour on
  this Mac; libstdc++ was not measured.
- K3 (injected +1e-6 in Y idx 17 of F02): met. Measured max |dy| 0.02941225000000003 px at G1, frame 49, pixel (0,0); predicted
  0.029412249999999918; relative difference 3.8e-15; dx exactly 0.
- Coefficient detail is in `receipts/iteration2/coefficients.csv` (all 36 per fixture per route, bit patterns, written token). For
  F03 the one changed coefficient is X idx 2: pre -0.00122271287007, written token `-0.00122`, read back -0.00122, abs error 2.71287e-6.

## Observations, with their limits

- The real writer changed 36 of 36 coefficients in F02 (ordinary values) and in F07. Per-fixture counts are in the table. Largest coefficient abs
  error is 4.6e-6 in the negative-value fixture F06 and 5e-7 in the positive-value fixture F05 (F02: 4.8e-6), consistent with 5 vs 6 decimals.
- Field error grows with frame: F10 gives 0.0006 px over frames 0-5 and 0.56 px over frames 44-49. On a 24-frame range (late24) the
  constructed fixtures give at most 0.058 px (F10), 0.037 px (F07). The 0.34 to 0.56 px values need frames up to 49 and are on constructed coefficients.
  These fixtures therefore do not reproduce or confirm the 0.36-0.38 px in the #265 report for a real movie. That needs the actual
  pre-write native coefficients of that run, which this task did not have and did not reconstruct.
- F05/F06 contain coefficients up to ~1e5 in the z-linear slot, so their shifts are about 1e8 px. They probe the format switches, not plausible motion.
  F08 and F09 probe the 12-character width (`1e-300` is written as `1.000000e-30`, 100000.5 as `1.00000e+05`); they are non-physical.
- All numbers are properties of the constructed coefficients and this toolchain's `snprintf`/`istream`. No claim about any real movie, CUDA, performance or science.

## Iterations retained

- Iteration 1 (`receipts/iteration1_json_escape_defect/`): numerically complete, but `summary.json` was invalid JSON because the reader's
  multi-line error text was not escaped. Kept as is. Iteration 2 reran with the escape fix and an `any_read_failed` field; its `samples_full.csv`
  and `coefficients.csv` hashes are identical to iteration 1's (`6da068ed…`, `720f1663…`). The fixture table was not changed.
- The follow-up table was added after observing iteration 1 and is labelled as such.

## Files

`fixtures.txt`, `PRE_RUN_CRITERIA.txt`, `FROZEN_BEFORE_RUN.txt`, `fixtures_followup_subnormal.txt`, `harness/roundtrip_oracle.cpp`,
`harness/summarize_receipt.py` (renders the tables above from `summary.json`), `run.sh`, `DESIGN_NOTE.md`, `receipts/`.

## Unresolved

Maintainer authorisation of a parity-breaking change to CPU STAR output (CPU/RELION `ad0b230` parity). Real pre-write coefficients
for the 10641 case are still needed to size the real-movie effect. No source fix is implied or prepared.
