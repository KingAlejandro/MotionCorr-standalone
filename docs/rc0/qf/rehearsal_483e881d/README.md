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
| 11. EER #208 replay | smoke only (revision 1): 3/3 cases PASS (`c04`, `b6`, `cc1`); 38 cases UNRUN | `raw/revision1/` |
| 12. Resident retry | revision 1: **4/4 single-GPU cases PASS** (retried 41/30/9/25 as #207); dataset part UNRUN (multi-GPU window) | `raw/revision1/` |
| 13. MRC #204 harness | **revision 1: PASS**, all 14 runs graded against #204 (errors 26/26 + 26/26 now pass; 6 KNOWN-F4) | `raw/revision1/` |
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
| Item 11 (#208 replay, 41 cases incl. up3 and F4-up2) | 1–2 h (smoke: 3 cases 85 s; not run in full) |
| Item 12 single-GPU + dataset | ≈ 6 min (measured) + ≈ 10 min in the multi-GPU window |
| Item 13 (#204 harness, all runs) | 5.4 min (measured) |
| **Total compute** | **≈ 3–4.5 h** on one single-GPU lane plus one multi-GPU window, excluding lock waits and macOS |

Items 0–10 alone are about 2–2.5 h; item 11 dominates the rest.

## Revision 1 (R-QF findings)

[R-QF](https://github.com/KingAlejandro/MotionCorr-standalone/pull/224#issuecomment-6233773780) requested
changes; tools and docs only. Same host, lane (GPU0 `GPU-eddb42fe…`, CPUs 96–103, GPU0 lock per run, bench
probe), source `483e881d` and binaries as above. Evidence: `raw/revision1/`.

| Finding | Fix | Check |
|---|---|---|
| P1 `--mixed --dry-run` executed real work | dry run returns before any mkdir/rmtree/symlink/launch on both paths | `probe_multigpu_dryrun.py` (stubbed side effects): new code 0 calls on G/L and mixed dry runs, control (mixed, not dry) caught; **the pre-revision code fails it on both dry-run paths** (`Path.mkdir`, `build_mixed_inputs`) |
| P2 `build.sh` hard-coded the workspace | every tool requires `QF_W` (and the lane variables); `build.sh` also requires `QF_SHA`, `QF_CPUS` and checks HEAD and a clean tree | unset `QF_W` → error, rc 1; nonexistent `QF_W` → `no source checkout`, rc 90 |
| P2 A2 dropped #123's NO_SESSION rejection | original two literals kept, prefix check added | `probe_matrix_fallback_witness.py`: new harness rejects all three fallback logs and accepts the clean one; **the pre-revision harness accepts the NO_SESSION log**. Matrix re-run on CUDA+nvCOMP: 16/16, 28/28 arms witnessed, gain control true |
| P2 refused compact arm did not prove non-publication | `refusal_publications()`: no corrected MRC, per-movie STAR or joint-STAR row | `probe_campaign_refusal.py` 5/5; e10028 G re-run PASS, `published_after_refusal: []` |
| P2 EER-MS disposition | runbook item 15; D10 pending, separate from D6 | docs |
| P2 items 11–13 not executable | `item11_eer.py`, `item12_retry.py`, `item13_mrc.sh` + `grade_item13.py`, `qf_lane_exec.sh` (runbook "Items 11–13") | runs below |
| P3 macOS wording | item 14 | docs; #223 is open, not in `483e881d` |

Driver runs on `483e881d`:

- **Item 13, full:** `grade.json` PASS in 5.4 min. All 14 recorded runs present with equal record counts (matrix
  36+36, refuse 2, compressed 49, options 10, errors 26+26, real 6, options runs 10). Every verdict equals
  #204's, except the errors records, which now all pass (#205). The six F4 `damaged` records still fail
  (KNOWN-F4). Real-data inputs matched #204's hashes. Grader self-test on #204's own JSONs: 40 mismatches,
  then PASS after those records are set to pass.
- **Item 12:** e10216 `--group_frames 1`: PASS. Retried 30 (#207: 30). Counter 30. `rec` has 29
  preparations, one warning and identical products. `fatal` exits 1 with the refusal message and publishes
  nothing. remaining-owned 0. frozen vs Q1 CUDA `1db86902` and frozen vs counter run: full and products
  identical. The first attempt omitted `--input-star` in the comparator call (harness bug, kept in
  `raw/revision1/superseded/`). The other three single-GPU cases also PASS: e10641 g1 (41 retried, counter 41, `rec` 40, fatal refused), e10641 g4 (9) and e10216 g4 (25), all equal to #207's record and identical to Q1's `1db86902`. **4/4 single-GPU cases PASS (≈6 min); the dataset part is UNRUN.**
- **Item 11, smoke:** `c04` (12963 g49 up1, auto vs float identical), `b6` (wrong-size gain, both arms fail
  as recorded) and `cc1` (frozen CPU vs Q1 CPU identical) PASS. The four damaged movies regenerated with
  #208's `eer_corrupt.py` equal #208's hashes. The other 38 cases are UNRUN here.
