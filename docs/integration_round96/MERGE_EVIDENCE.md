# Merge evidence — PR #110 round96 correctness foundation

Base `4c952b3f54479653512c4d208e09c9a8c02f3726`. **Draft; no merge requested.**

## Heads, by role

| role | head | note |
|---|---|---|
| **source / validation tree** | **`a0aa9032`** | last commit touching `src/ tests/ tools/ CMakeLists.txt test-data/ .github/` |
| evidence scripts | `a0aa9032` | same commit; `docs/integration_round96/scripts/` also moved later at `e1ca679` (audit scripts only, ungated) |
| branch HEAD | `e1ca6798` | everything after `a0aa9032` outside the two rows above is evidence and prose |
| CI green at | `a0aa9032`, `181ca204`, `f416d16b`, `95f0e4bc` | all four: Build & Smoke Check **success**, CUDA compile only **success** |

`src/**` has not changed since the composed head `07a6a77` was validated.

## Checks actually run

| check | where | result |
|---|---|---|
| Combined CTest suite | cpu64, lock, `taskset -c 32-63`, `membind=1`, ≤16 | **17/17** |
| Fail-closed controls | same | **8/8** |
| `--canonical` side effects | same | none; `test-data/known_motion` clean |
| Negative control vs BASE `src/` | same | builds, runs, **4/17 fail** — exactly `DefectParser`, `DamagedMovie`, `WriteFaults`, `ImageWriteFaults` |
| Healthy all-24 A/B, CPU | same | 24/24 images identical, 341,735,520 px, 25 STARs (path-normalised) |
| **Native CUDA all-24** | **SCARF `3511135`, exclusive `gn3001` A100** | **24/24 pixel-identical, 341,735,520 px, 25/25 STARs**, on-device witness pid 410748 |
| Native controls | SCARF `3511136` | decoded-reader 24/24; failure exit 1, joint STAR withheld; resume exit 0, pixel-identical |
| Native CUDA, 2nd platform | VM GPU3, user-authorized exception | identical result on different silicon |
| Default CUDA configure | 4-GPU VM | **FAILS** — pre-existing, reproduced, not fixed here |
| PDF retained-evidence audit | cpu64, retained pairs, no re-run | rendered difference is the embedded output path only; **no plot datum differs**; `overall: FAIL` retained |

## Reviews

| review | scope | verdict |
|---|---|---|
| code / spec | `16de2583..49d9dbe` | **READY_TO_MERGE**, no P1, no P2 |
| code / spec, bounded delta | `1c590ba..95f0e4bc` in `tools/test_ci_fail_closed.py` | **CONFIRMED** comment-only (AST and token-stream identical, 253 stmts, 66 assertions, 8 controls unchanged) and the comment's claim accurate |
| licence / scope | `a224bc50..49d9dbe` | **LICENSE_COMPLIANCE_PASSED** + **SPEC_CONFORMANCE_PASSED** |

Two existing reviewers only; no new reviewer or owner was introduced.

**Coverage gap, stated:** `docs/integration_round96/scripts/compare_native_products.py` (P3-2 fix at `a0aa903`, audit scripts at `e1ca679`) has **not** been re-read by a reviewer. It is referenced by no CI job, no CTest and no tool — verified by grep over `.github/`, `CMakeLists.txt`, `tools/`, `tests/`, `test-data/` — so it gates nothing and produced evidence, not verdicts.

## Residual maintainer decisions

Only items actually reproduced or genuinely open. The already-reviewed
`src/image.h` semantic merge, the required-NumPy test dependency and the
historical `generator_sha256` provenance are recorded in `REQUIREMENTS.md`
§E/§K and do **not** need a second generic ADR approval.

| # | decision | status |
|---|---|---|
| 1 | Scoped `CMAKE_CUDA_ARCHITECTURES` fix under **#72/#18** | reproduced blocker; deliberately **not** fixed on this branch |
| 2 | Root `WORKER_STATUS.md`: tracked (#72/#92/#99) or ignored (#98) | direct policy collision between integrated branches; resolved in #98's favour here, all records archived |
| 3 | #97/#100 upstream-parity divergence | conditional; #100 **not** imported |
| 4 | Whether the VM GPU3 use stands as a user-authorized exception | Alex authorized 07:22:00.189Z; coordinator warning retracted; recorded |

## Recommendation

**Merge #110 before the GPU tranche.** It is the smallest reviewed unit that
makes the tranche measurable: it supplies the fail-closed inventory the later
work is graded by, and it is the only tree on which #72, #92, #98 and #99 have
been validated *together* with a native CUDA baseline. Landing #107/#108/#106 on
top of four separate branches would re-open the composition hazard this branch
already found once — #72's restructure silently reinstating an overwrite while
every test stayed green.

Order within the tranche is unchanged: **#102 → #101 → #105 → #103**, retesting
the resulting tree after each step, then #97 once decision 3 is ruled on.

## Preserved, not waived

Four PDF differences with **`overall: FAIL`**; `km_local_noisy` **FAIL** and
excluded from aggregate acceptance; the pre-existing **default CUDA configure
failure**; the **NumPy `BUILD_TESTING=ON`** dependency on GPU hosts. No gate,
threshold or tolerance was relaxed anywhere on this branch — every movement is
a tightening.
