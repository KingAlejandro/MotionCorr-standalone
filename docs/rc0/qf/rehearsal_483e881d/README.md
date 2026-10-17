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
| 11. EER #208 replay | **revision 2: 41/41 recorded cases PASS** (`o1n` replaced by the guard-removed control); 4/4 negative controls rejected; guard-removed control o1n/o5n PASS | `raw/revision2/` |
| 12. Resident retry | **4/4 single-GPU cases PASS** (revision 1; retried 41/30/9/25 as #207); **dataset part PASS** (revision 2, GPU0 + GPU2: d1/d2/dshim, #207's asymmetric dpoison, dpoison_both) | `raw/revision1/`, `raw/revision2/` |
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
| Item 11 (#208 replay, 41 cases incl. up3 and F4-up2, negative controls) + guard-removed control | ≈ 25 min + ≈ 6 min (measured, revision 2) |
| Item 12 single-GPU + dataset | ≈ 6 min + ≈ 1 min with two GPUs (measured) |
| Item 13 (#204 harness, all runs) | 5.4 min (measured) |
| **Total compute** | **≈ 2.5–3 h** on one single-GPU lane plus one multi-GPU window, excluding lock waits and macOS |

Items 0–10 are about 2–2.5 h; items 11–13 add about 45 min.

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

## Revision 2 (R-QF round 2)

[R-QF round 2](https://github.com/KingAlejandro/MotionCorr-standalone/pull/224#issuecomment-6234322411)
left finding 6 partly open. Tools and docs only. Same source `483e881d` and binaries. Lanes: GPU0 + CPUs
96–103 under the GPU0 lock; the item 12 dataset part also used GPU2 `GPU-063e5232…` + CPUs 112–119, holding
the GPU2 lock (all four GPU locks and the bench lock were free, with no compute process, when it started).
Evidence: `raw/revision2/`.

**Item 11.** #208's per-movie predicates are restored (script header). The synthetic fixtures are bound to a
frozen recipe (`item_records/eer_synth_recipe.json`): every run regenerates them and compares hashes. An
independent strip decode records encodings 65000/65001/65002, detectors 4K/2K, 240/49 152/196 608 fractions
and group maxima of 65 532 (o2), 65 535 (o3) and 65 536 (o1, o4, o5); decoded electron counts equal the recipe.
Results:

| Run | Result |
|---|---|
| first pass (superseded), all non-heavy cases | 32 PASS. b1–b5 FAILED on a **harness error**: movie 3 must be #208's "healthy B" (the second Falcon3 movie), not a second copy of A. The payload check against #208's hashes caught it (`raw/revision2/superseded/`) |
| b1–b5 re-run after the fix (then repeated in the final pass) | **5/5 PASS**: published sets, joint STAR, frame counts (b5: 34), D6 warnings (b3 frame 701, b4 frame 901), error messages, auto = float, and every MRC payload hash (healthy and damaged) equal to #208's `1db86902` record |
| heavy cases (m1, m2, c15, c16) | **4/4 PASS** (F4 up2 full 144 groups and 100 groups; Falcon3 and 12963 up3) |
| **final pass**, all non-heavy cases with the committed harness, `--negative-controls` | **37/37 PASS**, 4/4 negative controls rejected (`raw/revision2/item11.log`, `item11-summary-final.json`). With the heavy run: **41/41** |
| negative controls (real outputs, mutated copies) | 4/4 rejected: b6 planted per-movie + joint STAR (`exited 1 but wrote a completion STAR`), b2 one float payload byte (`payload … != #208`, `auto vs float MRC payloads differ`), o1 MRC planted in the refused compact arm (`refused but published`), b3 warning removed (`D6 skip warnings at [] != #208 [701]`) |
| guard-removed control (`item11_noguard_control.sh`, mutant `8ba5bc0f…`) | o1n and o5n PASS: without the guard, auto takes compact and its products **differ** from float (compare rc 1), so the replacement fixtures reach the wrap |

**Item 12 dataset part** (GPU0 + GPU2, `raw/revision2/item12-dataset.log`, `item12-dataset.json`):

| Arm | rc | Dataset | Checks |
|---|---:|---|---|
| d1 (1 worker) | 0 | PASS | 4 MRC + 4 STAR + joint STAR merged |
| d2 (2 workers) | 0 | PASS | identical to d1 (30 files) |
| dshim (counter) | 0 | PASS | identical to d1; shim counted 25 + 16 resident preparations = retried (as #207) |
| dpoison (wrapper, fault on GPU2's worker only) | 3 | FAIL, not ready | worker rcs [0, 1]; w1 log has `fault=on`, the injected fault and the refusal, keeps its tutorial movie, no 10641-B product; w0 `fault=off`, complete; no merged tree; cleanup complete |
| dpoison_both | 3 | FAIL, not ready | worker rcs [1, 1]; both logs carry the injected fault and refusal; each keeps its tutorial movie; nothing merged |

`probe_item12_dataset_grader.py`: rc 127 with no files (three expectations), a FAIL status without worker
status, and a complete-looking FAIL status where no fault ran are all rejected.

**Item 13.** The driver now exits with the grader's status. `probe_item13_exit.sh`: unmodified results →
driver rc 0; one verdict flipped → driver rc 1.
