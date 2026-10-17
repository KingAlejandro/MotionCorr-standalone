# QF rehearsal on composed main `483e881d` (W-QF-PREP, #198)

Source: `483e881d9a6a352dba3268dac0f8c729364860b5` (main after #205, #199 and #217), a git checkout on 4GPUs from a
bundle of `origin/main`, 0 modified files at build and CTest time. Host 4GPUs: A100 80GB PCIe, driver 570.86.10,
CUDA 12.8.61, g++ 13.3.0, CMake 3.28.3, Python 3.12.3 + NumPy 2.5.3, Ghostscript 10.02.1, nvCOMP 5.3.0.16, THP
`madvise`. Lane: GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54` (pinned by UUID), CPUs 96–103, GPU0 correctness
lock held for every GPU run, bench lock probed before every build/batch. Correctness only: no timing claim.

The tools are the committed [`../tools/`](../tools/) files (hashes in `raw/tool-sha256.txt`; the matrix JSON
records its own harness, comparator and fixture hashes).

## Result

| Runbook item | Result | Evidence |
|---|---|---|
| 0. Builds (Release, `-O3 -DNDEBUG`) | 3/3 rc 0. CPU `57256b87…a2b0ea`, CUDA `7d2a0b17…dd4ad4`, CUDA+nvCOMP `f8bd3740…e899b` | `raw/build-info.txt` |
| 1. CTest CPU | **68/68 PASS**, 0 skipped; `validate_test_collection` PASS; `test_ci_fail_closed.py -v` rc 0 | `raw/ctest/` |
| 2. CTest CUDA | **101/101 PASS**, 0 skipped; validator PASS | `raw/ctest/` |
| 3. CTest CUDA+nvCOMP | **104/104 PASS**, 0 skipped; validator PASS | `raw/ctest/` |
| 4. F3/F3b (#205) | `TruncatedMrcMovie`, `TruncatedGainDefect` (all builds), `TruncatedMrcMovieCuda`, `TruncatedGainDefectCuda` (both CUDA builds) PASS | inside 1–3 |
| 5. Route/product campaign (reduced) | **5/5 PASS**: tutorial G/L, EER 12963 G, int16 MRC 10216 G, float MRC 10028 G | `raw/campaign/` |
| 6. CPU identity vs Q1 `1db86902` (`dd86cd41…6b26439`) | **5/5 identical**, products-only **and** strict all-files (logs included) | `ref_cpu_vs_cpu` in each case JSON |
| 7. #178 fallback | UNRUN (not in the rehearsal scope) | — |
| 8. Multi-GPU | **dry run only**: GPU1 was in use by W-QM, so the "all four lanes free" condition for a 2-worker smoke never held. Commands and device/CPU assignment printed correctly for G/L × w1/w2/w4 | `raw/multigpu/multigpu-dryrun.txt` |
| 9. Adapted #123 matrix | **16/16 rows PASS on both CUDA executables**; 28/28 arms UUID-witnessed on GPU0 each; gain-effect control `differs: true`; routes 23 compact / 16 float as declared; inputs byte-identical to #123's runs of record | `raw/matrix/` |
| 10. `CpuDoseSymmetry` (#220) | N/A: #220 not merged at `483e881d` | — |
| 11–13. EER/retry/MRC item harnesses | UNRUN (only their CTests and campaign rows ran) | — |
| 14. macOS | UNRUN here (other worker) | — |

### #205 + #217 composed

This is the first native run with both. Every #205 truncation test and every #217 nvCOMP test passes in the same
CUDA+nvCOMP build: `CudaNvcompAcceptanceFailures`, `CudaNvcompReconstructionFailures`, `CudaAdler32`,
`NvcompAcceptanceDiagnostics`, `NvcompGuards`, `Adler32*`. On valid input, the tutorial movie took the nvCOMP
route under `--ingest auto`, and its products are identical to the compact and float routes (G and L). The CPU
build's products and logs are byte-identical to Q1's `1db86902` in all five cases, as the composition predicts
(#200, #205, #210 and #217 change failure paths only).

### Campaign detail (config G unless stated; `--use_own --dose_weighting … --seed 1 --j 8`, family options from `docs/workload_corpus/families.json`)

| case | auto route | compact arm | float arm | products auto vs compact / float | strict all-files auto vs compact / float | CPU vs Q1 CPU | Tier B relative RMSE (diagnostic) | peak RSS auto / compact / float / CPU (GiB) |
|---|---|---|---|---|---|---|---|---|
| tutorial | nvcomp | compact | float | PASS / PASS | differs / differs (route log lines; PASS with declared allowance) | PASS (strict) | 0.007096 | 0.34 / 0.84 / 1.51 / 2.71 |
| tutorial L | nvcomp | compact | float | PASS / PASS | differs / differs (declared allowance PASS) | PASS (strict) | 0.008358 | 0.34 / 0.84 / 1.52 / 2.92 |
| e12963 EER | compact | compact | float | PASS / PASS | **PASS** / differs (allowance PASS) | PASS (strict) | 0.022727 | 2.30 / 2.30 / 3.57 / 5.89 |
| e10216 int16 MRC | compact | compact | float | PASS / PASS | **PASS** / differs (allowance PASS) | PASS (strict) | 0.016591 | 2.04 / 2.01 / 3.89 / 7.49 |
| e10028 float MRC | float | **refused** (expected: pinned compact on an ineligible movie) | float | — / PASS | — / PASS | PASS (strict) | 0.013917 | 1.51 / — / 1.44 / 2.11 |

Inputs (SHA-256, all matching `docs/workload_corpus/corpus.md`): tutorial `20170629_00026` `f989391b…54ae3`
(gain `8919cdc7…1acd1`), 12963 `…014501_EER.eer` `3fc5feb6…403f5` (gain `6d4f3e5f…34050`), 10216
`…1739_Fractions` `f399bd30…23a56`, 10028 `031_movie` `8ce47964…c7213` (full values in
`raw/campaign/summaries/inputs-G.json`). Every GPU arm that processed a movie was seen by nvidia-smi on GPU0 and no
other device.

The strict comparison differs exactly where the two arms took different routes, and is identical where they took
the same route (auto = compact for EER/MRC). That shows the comparator does observe the route log lines. The
Tier B values equal Q1's recorded values for the same cases (0.007096, 0.008358, 0.02273, 0.01659, 0.01392). This
suggests the CUDA products are also unchanged since `1db86902`. It is a match of five rounded numbers, not a byte
comparison.

## Findings

No composed-main defect and no flaky test in this rehearsal: every test passed first time, including
`ProfilingKit` (111–113 s) and `MultiGpuScheduling`, the two load-sensitive tests from Q1.

Script problems found and fixed in `tools/` (none in product code):

1. **`product_campaign.py` (new compact arm):** it required a GPU witness from the `--ingest compact` arm even when
   that arm was correctly refused during routing, before nvidia-smi can list the process. e10028 was therefore
   marked FAIL although the product behaviour was right. Fixed: on an expected refusal the witness is recorded,
   not required. The first attempt is kept in `raw/superseded/`.
2. **Matrix source root:** run from `$QF_W/tools`, the ported harness would have recorded no source commit.
   `SOURCE_ROOT` now honours `QF_W`.

After both fixes, the matrix and the whole campaign were re-run with the committed tools (`raw/rerun.out`). The
first-pass logs, which were identical in outcome, are in `raw/superseded/first-pass/`. Process note: between the
first-pass campaign and the re-run, a cleanup in the scratch checkout deleted the tracked
`docs/rc0/decoder_trust_and_dependencies.md`. It was restored before the reported runs. Builds and CTest ran
before the deletion, and the reported matrix and campaign runs record 0 modified files.

Runbook observations for the frozen-SHA run:

- `docs/issue85_laneC/compare_output_trees.py` on main still cannot grade `_noDW/_EVN/_ODD` or mixed-shape trees
  (Q1 finding 3). The #123 matrix therefore uses its own vendored comparator, and the #178 rows use
  `tools/profiling/lib/identity.py`.
- `--ingest compact` on a float MRC is a deliberate refusal. Any campaign driver that treats nonzero rc as failure
  must special-case it, as `product_campaign.py` now does.

## UNRUN in this rehearsal

#178 fallback (item 7), the multi-GPU executions (item 8), families 10361/10474-F3/10164 and configs L other
than tutorial (item 5), the item harnesses of #204/#207/#208 (items 11–13), `CpuDoseSymmetry` (item 10, #220
unmerged), macOS (item 14), any second venue, timing.

## Estimated QF wall-clock on the frozen SHA

Measured here: builds 6 min, CTest 19.4 min (CPU 5.4, CUDA 7.0, nvCOMP 7.0), #123 matrix 22 s per executable, and
campaign cases 21–48 s each (5 arms, small families).

| Step | Estimate |
|---|---|
| Builds + CTest ×3 | 26 min (measured) |
| Campaign, 7 families × G/L with ref CPU | 15–25 min (14 cases; 10361/10474-F3 have the largest CPU arms, Q1 RSS up to 11 GiB) |
| #123 matrix ×2 executables | 1 min (measured) |
| #178 fallback + injected sweep | ≤ 30 min (not rehearsed; ≈ 20 tutorial runs plus a sweep of up to 16) |
| Multi-GPU G/L 1/2/4 + mixed | 30–45 min once all four GPU locks and the bench lock are free (Q1: ≈3 min per invocation) |
| Item harnesses 11–13 at their PR heads | 1–3 h (not rehearsed) |
| **Total compute** | **≈ 3.5–5.5 h** on one single-GPU lane plus one multi-GPU window, excluding lock waits and macOS |

Without items 11–13, the core QF (items 0–10) is about 2–2.5 h.
