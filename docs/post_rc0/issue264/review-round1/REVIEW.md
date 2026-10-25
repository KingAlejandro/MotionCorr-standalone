# Independent review, round 1: DRAFT PR277 (#264 centred distortion-domain guard)

Reviewer: fresh delegated task, read-only. Head reviewed: `91380b3f9c30cf2060311748e9e60e68670dc22e`
(production/test source `4b0e4e73`; `git diff 4b0e4e73 91380b3f -- src tests tools CMakeLists.txt` is empty).
Base `3691374061f782bc84531fd1c79d017ddcb5a7c2`. Host: macOS arm64, Apple clang 21, one compile at a time, load ~3.5 of 14 CPUs, `OMP_NUM_THREADS=1`.
No push, PR, comment, Notion write, remote or GPU job. Scratch: this directory only. CI was not polled.

## Verdict

**No blocking defect in the production change.** Guard geometry, coordinates, units and the production call are correct on the evidence below.
Two non-blocking test gaps (F1, F2) should be closed before any merge recommendation. **DRAFT stays DRAFT: native qualification is UNRUN.**
No merge recommendation while qualification is pending.

## What I checked and found correct

- **Math.** The model is quadratic in (x,y) (`micrograph_model.cpp:35-54`: terms 1, x, x², y, y², xy, each with a time polynomial). A forward difference along x
  is `a1 h + a2(2xh+h²) + a5 y h`, along y `a3 h + a4(2yh+h²) + a5 x h`: affine in (x,y). |affine| over a rectangle is maximal at a corner, and the corners
  `ix∈{0,last_x}, iy∈{0,last_y}` are real pixels. The 2×2 corners × 2 axes × both components × all frames in `local_motion_guard.h:17-42` is therefore exact, not an approximation.
- **Valid-pair domains.** `last_x = nx-1-(axis==0)`, `last_y = ny-1-(axis==1)`, so horizontal pairs end at `nx-2` and vertical at `ny-2`, never leaving the image;
  length-1 directions are skipped. Matches the README rectangles.
- **Coordinates match reconstruction.** CPU `(RFLOAT)ix/nx - 0.5` (`motioncorr_runner.cpp` ~4400-4410, 4573+), CUDA `(float)ix/(float)nx - 0.5f` (`cuda_realspace_dw.cu:150-151`),
  header contract `micrograph_model.h:49`. The helper evaluates the same expression in `Real`; for `RFLOAT=float` the single rounding is identical to the runner's double-subtract-then-round.
- **nx, ny, frames, units.** At the guard (`motioncorr_runner.cpp:3914-3917`) `nx,ny` are the post-early-binning alignment dims (3158-3166), the dims `Iref`/`Iframes` have at reconstruction;
  fit `z` is the per-frame index (`patch_frames`, 3824/3833) and the guard loops `z=0..n_frames-1`, with `n_frames` the ungrouped frame count (2173). Shifts are in alignment pixels;
  `writeModel` rescales only the exported copy (1487-1495). Grouping and binning therefore need no extra handling. Frame 0 is always 0 in this model (every term carries z), so it is unobservable.
- **Call site.** One guard exists (`git grep`), in the path shared by CPU and CUDA. Threshold constant, strict `> 3`, message text and `goto skip_fitting` are untouched. I compiled the edited
  `motioncorr_runner.cpp` TU alone (CPU Release, own build dir, `make -j1 src/motioncorr_runner.cpp.o`): rc 0, only the existing `rwSPIDER.h` sprintf warnings (`runner-object-build.log`).
  This is a compile of one TU, not a full application build.
- **Inventories.** `CMakeLists.txt:213-215`, `tools/validate_test_collection.py:46`, both mock inventories in `tools/test_ci_fail_closed.py` (198, 279). The mock additions are necessary:
  running the test from a copy of this worktree with them removed fails ("Missing required test(s): LocalMotionDistortionGuard", 37 failures). An earlier attempt from a bare `git archive`
  tree was confounded by the missing-`.git` trap and is discarded.
- **Licence/scope.** New files carry `SPDX-License-Identifier: GPL-2.0-or-later`, no dependency, original runner notices untouched, diff limited to the guard, helper, test, inventories, docs.
- **Hash bindings.** `host_results.json` legacy runner sha `8a3a1ad8…` equals `git show 36913740:src/motioncorr_runner.cpp`; recorded test sha `7b939e06…` equals the file at HEAD;
  the four `cmake-*.log` sha256 in `cmake-host-evidence.json` match the files. The author's CMakeCache points at the author worktree and Release (as claimed).

## Independent commands and results (all at HEAD 91380b3f)

| Check | Result |
| --- | --- |
| `clang++ -std=c++17 -O2 -Wall -Wextra -Werror` repo test | PASS 51/51 |
| Same with `-fsanitize=address,undefined` | PASS 51/51 |
| `docs/post_rc0/issue264/verify_host.py --out <mine>` | legacy exact block exit 1 (45 fail), fixed exit 0, uncentred mutant exit 1 (37), invalid-last-pair mutant exit 1 (10); header/stdout/hashes identical to the author's record |
| Legacy block with `stop_above` honoured (my variant, wrapper otherwise unchanged) | 44 fail: the 45 is not an artefact of the wrapper's hard-coded 3 |
| `tools/test_ci_fail_closed.py -v` with `~/.local/bin/python3` (NumPy) | 8/8 PASS. With default `python3` (no NumPy) 5 fail on `import numpy`: interpreter, not code |
| My harness `h/harness.cpp`: the **real `getShiftAt` body** (sed-extracted from `micrograph_model.cpp:35-54`, 18 random coefficients X/Y, shapes 1x1…100x80 incl. 1xN/Nx1/2x2, 1-6 frames) vs a brute-force scan of every in-image pair using the **reconstruction's optimised formula** | double: 4400 cases, worst rel err 2.5e-14; float: 4400 cases, worst 9e-6; 0 strict-`>3` decision mismatches in both |
| Same harness on mutants (uncentred, last pair, swapped axes, x-only, one component only) | all fail ordinarily (nonzero rc, hundreds to thousands of mismatches) |
| Repo test on 14 extra mutants (uncentred, last pair, no early exit, swapped axes, x-only, x-component-only, low corners, forward-step bug, integer-division, no abs, …) | all caught except two: `>=` early exit (F1) and starting at z=1 (equivalent: frame 0 is identically 0) |

## Findings

**F1. Strict-threshold semantics of the helper's early exit are not pinned (low-medium, test gap).** `src/local_motion_guard.h:40` `if (largest_delta > stop_above) break;`
changed to `>=` passes the repo test (51/51). It is decision-affecting: shift `z*300*x`, nx=100, 3 frames: frame 1 delta is exactly 3, frame 2 is 6. Strict returns 6 (reject);
the `>=` mutant returns 3 (accept) (`h/gte_case.cpp`). The test's threshold witnesses use 2 frames (`tests/test_local_motion_distortion_guard.cpp:69`), so an exactly-3 first frame is never followed by a larger one.
The runner-side decision (`motioncorr_runner.cpp:3917`) is restated as `got <= 3.0` inside the test (line 71), so a `>` to `>=` change in the runner is also invisible to it.
Fix: add one case with nf>=3 where frame 1 is exactly 3 and frame 2 exceeds it, expecting the larger value returned.

**F2. No test ties the helper to the production model, coordinate formula or call (low-medium).** The test's `Polynomial` (lines 15-16) uses a different coefficient order and a common time factor;
it never touches `ThirdOrderPolynomialModel`, and nothing exercises the runner's `(*model, nx, ny, n_frames, 3)` call (an `nx`/`ny` swap or `n_frames-1` there would pass every test).
The `ix/nx - 0.5` convention is now restated in the helper, CPU reconstruction, CUDA kernel and the test with no coupling check, the drift pattern in the restated-guard memory.
I found no defect: my retained harness (above) agrees with the real `getShiftAt` body and the reconstruction formula. Suggested: either a CTest linked to `motioncorr_core` that uses a real
`ThirdOrderPolynomialModel`, or the native witness N3 below.

**F3. Non-finite models are accepted (informational, pre-existing, not a regression).** A NaN or `Inf-Inf` shift leaves `largest_delta` at 0 because `0 < NaN` is false; the legacy block
behaves identically (`h/nan.cpp`, both print `rejected=0`). Out of scope for this fix; the later RMSD check is the only remaining defence. Note only.

**F4. Evidence limits (informational).** All measured evidence is macOS/Apple clang on a header-only helper. nvcc/gcc compilation of the changed runner TU and CUDA configs rely on CI (parent-watched),
which is compile-only evidence. No retained native log in `docs/` contains "could not fit a reasonable local motion model", so no existing native run is a flip witness. The README's intentional-difference
statement (RELION `ad0b230` parity changes only for models whose wrong-domain and correct-domain decisions differ) is accurate and needs the maintainer sign-off required by plan §9.2/§9.4;
that sign-off is not in the branch and I have not assumed it.

## Statuses I keep unchanged

Helper regression (host, exhaustive reference): PASS. Native fitting/reconstruction/publication, CUDA execution, full CPU/CUDA/nvcomp CTest, full-collection validation: **UNRUN**
(author's partial collection FAIL is correctly retained as FAIL, not a product regression). pbzip2-dependent tests UNRUN on this host. Science/accuracy: not claimed.

## Minimal frozen native validation matrix for a claim

Freeze the candidate SHA, base `36913740`, binary and input hashes, UUID, CPU affinity, lock names, build flags before running; one failed iteration is retained, not repaired in place.

- **N1 (classification §9.4, CUDA/shared source).** Exact-SHA full CTest on the three configurations (CPU, CUDA, nvcomp) on 4GPUs under the GPU correctness lock and compile lock (j<=2), with
  `validate_test_collection.py` PASS and `LocalMotionDistortionGuard` present and passing in each.
- **N2 (unchanged-where-unaffected).** Candidate vs base `36913740`, same inputs, CPU and one CUDA device (UUID-selected), the 24-movie tutorial set: output trees equal under `compare_output_trees`
  (with the usual log/timestamp allowances, unrewritten-STAR trap noted), and **zero** "could not fit a reasonable local motion model" lines in either arm. This supports "no change where the guard accepts
  both ways" only.
- **N3 (flip witness through the real runner).** One synthetic periodic known-motion fixture per direction whose fitted model straddles the threshold (legacy accepts and new rejects; legacy rejects and
  new accepts), run CPU and CUDA on base and candidate, with witnesses: stderr line present/absent, STAR local-model block absent/present, global-only output equals the no-local-motion run.
  Genuine movies rarely approach 3 px/pixel gradients, so this likely needs extrapolating-fit fixtures (few patches); if no such fixture can be built, keep the claim at helper-level plus N1/N2 and state it.
- **N4 (negative control).** The same N3 run with the uncentred mutant built in must fail the flip witness (a control that cannot fail proves nothing here).
- **Not needed:** timing. No timing claim is made, and none should be.

## Recommendation

Keep DRAFT. Next bounded action: add the F1 case (and, if cheap, the F2 real-model test), then run N1-N2 on the new exact SHA; N3/N4 only if a fixture is feasible, otherwise record that limit.
Re-review the delta as a new delegated task.

Retained artefacts here: `fixed-test`, `asan-test`, `verify_host_out/`, `legacy_honour_stop/`, `m_*/` and `m2_*/` mutants, `h/` harnesses and `gte_case`/`nan` probes, `cmake/` (own build dir), logs, `hashes.txt`.
