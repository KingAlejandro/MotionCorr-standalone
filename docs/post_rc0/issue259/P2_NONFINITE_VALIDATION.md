# PR #270: reject nonfinite regression pixels

Base: `7e1c868ce9389bac32f9984e9f5b3b1f674bbf68`. The fresh implementation
worktree started clean at `c8844894c7c6366abf297699b5312e4b775eb5b0` and was
fast-forwarded only to the fetched PR head; expected, live, fetched and local
heads agreed. Implementation revision: the commit containing this note.
Read `AGENTS.md`, live issue #259 and its latest boundary/measurement comment,
PR #270 description/discussion (no reviews or inline comments), and the prior
`t3-c5846551/build/review270/review.txt` including its NaN stand-in reproducer.

`fabs(NaN) >= 0.05` is false, so an all-NaN output previously passed all seven
cases. The CUDA regression now calls a small shared **test-only** predicate
which rejects nonfinite actual **or** expected values before subtraction. It
throws with the case, pixel coordinates and both values; the test catches the
exception, prints `FAIL` and exits 1, including in `--expect-mismatch` mode.
Finite error calculation and the exact `>= 0.05` threshold are unchanged.

`RealspaceBorderValidation` exercises this same predicate without CUDA or
`motioncorr_core`: eight finite controls (matching, below/exactly at/above the
threshold, both error signs) and 15 nonfinite combinations (NaN and both
infinities on either side alone and all nine pairs). Checks remain active under
`-DNDEBUG`. Original seven CUDA cases and x/y float-floor mutant registrations
are unchanged. No production warp, coefficients, weights, fallback, metadata,
publication, policy, tolerance or dependency changes. New support has
GPL-2.0-or-later SPDX notices; existing license/provenance notices are unchanged.

## Local verification, 2026-10-22

Host: SCMAC-7L9P2F, Darwin arm64, Apple clang 21.0.0, 14 CPUs, 24 GiB RAM.
Occupancy checked at 10:46:03 UTC: load 16.26/18.47/22.26; unrelated processes
left alone. All checks sequential, with `OMP_NUM_THREADS=1` and
`OPENBLAS_NUM_THREADS=1`; CMake parallelism limited to 1. No timing claim.
Scratch retained in this worktree's `build/p2-border-validation/` (new directory;
no historic evidence overwritten).

Run from the repository root:

```sh
clang++ -std=c++17 -O3 -DNDEBUG -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  tests/test_realspace_border_validation.cpp \
  -o build/p2-border-validation/validation-sanitized
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 build/p2-border-validation/validation-sanitized
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python3 build/p2-border-validation/run_controls.py
git diff --check
```

- **PASS:** standalone actual-predicate controls, exit 0:
  `PASS: 8 finite controls and 15 nonfinite rejections`. No ASan/UBSan findings.
- **PASS:** three scratch header mutants (no finite guard, actual-only guard,
  expected-only guard) compile at `-O3 -DNDEBUG` and each fails the same host
  control with exit 1: `accepted nonfinite actual or expected pixel`.
- **PASS:** original actual test body with minimal host Image/model/CUDA API
  stand-ins returning an all-NaN image reproduces `PASS: 7 cases match`, exit 0.
  Revised actual test body with that same stand-in exits 1 in normal and
  `--expect-mismatch` modes: `FAIL: last column: nonfinite pixel at x=0 y=0,
  got nan want 0`. Only the two production includes are replaced; comparison,
  cases and exit logic come from the actual test source. This exercises host
  validation logic, **not the GPU warp**. `controls.json` retains exact compiler
  and run argv, exits, output, source SHA-256s and stand-in/mutant binary hashes.
- **PASS:** diff whitespace check; byte comparison confirms all seven cases,
  x/y mutant registrations, production `.cu`, LICENSE, COPYING and source
  manifest unchanged relative to the base.
- **Initial CMake attempt failed:** configuration/CTest registration. Command:
  `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 cmake -S . -B build/p2-border-validation/cmake -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON`.
  Exit 1: selected Python 3.14.8 lacks NumPy, required by existing CMake checks.
  System Python also lacks NumPy. No dependency or policy workaround applied.

Native CUDA compilation/execution, native old-floor mutant runs, scientific
qualification and performance are **UNRUN** (no local nvcc). No retained native
results are requalified by this change and no combined-#272 evidence is used.
No push, merge, GitHub comment, Notion write, remote job or GPU job performed.

## Parent registration check

The existing `/Users/alex.konstantinov/.local/bin/python3` has NumPy, so the
parent completed the registration check at `838660e5` without installing or
changing dependencies. With all three thread caps set to 1:

```sh
cmake -S . -B build/p2-border-validation/cmake -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3
cmake --build build/p2-border-validation/cmake --target realspace_border_validation --parallel 1
ctest --test-dir build/p2-border-validation/cmake -R '^RealspaceBorderValidation$' -j1 --output-on-failure
```

Configure and focused build **PASS**; focused CTest **1/1 PASS**. Configure
retains the existing missing-pbzip2 waiver for unrelated compressed-MRC cases;
those cases were not executed. Full CTest and native CUDA remain **UNRUN**.
This documentation follow-up changes no tested source or CMake registration.
