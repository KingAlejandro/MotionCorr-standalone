# #262 four-arm CCF DC experiment — PARTIAL, native campaign still running

Status at 2026-10-22T20:45Z: **PARTIAL / live-job handoff.** Phase 0 iteration 2
PASSES; Tier A is complete; Tier B is about 48% evaluated; Tier C has not started.
No M3 recommendation is made. Native cost is UNRUN. Exit 0 is not a truth PASS.
Endpoints, matrix and order are frozen in [FREEZE.md](FREEZE.md) (`b6cb4d76`,
revision for iteration 2 in `f3ce649a`).

## Sources and binaries

| Item | Identity |
|---|---|
| Base (#273 composition) | `805d9de27898b4a10e6212e65098d5995a40fdb1` |
| Iteration 1 source (retained FAIL) | `59ff5811d379bfd0f13c189fec7f54b608e61678` |
| Iteration 2 source (all current evidence) | `3eee0a4b4e367f9b57f950c440c89679a5ec9c93`, archive SHA-256 `b7152c0a...8d49c` |
| Production diff vs base | `CMakeLists.txt`, `src/experiment_ccf_dc.h`, `src/motioncorr_runner.cpp`, `src/acc/cuda/cuda_alignpatch.cu` (default-off) |
| cpu-exp / cuda-exp `motioncorr` | `d6d76123...e20533` / `35f0c674...5f0c7` |
| cpu-plain / cuda-plain `motioncorr` | `3ba47d26...a315` / `3da31378...1935` |
| Toolchain | GCC 13.3.0, CMake 3.28.3, CUDA 12.8.61, sm_80, Release `-O3 -DNDEBUG`, `USE_NVCOMP=OFF` |

Full binary hashes: `raw/iter2-3eee0a4b/phase0-build.tar.gz` (`build/binary-hashes.txt`).
Rebuilt binaries differ from iteration 1 even where sources are identical
(absolute build paths are embedded), so no iteration-1 binary is reused.

## Phase 0 (operator and build controls)

- **Iteration 1 (`59ff5811`): mutant-control FAIL, retained.** Stage oracle
  passed on CPU and CUDA builds; 7/10 restoring mutants were killed; the three
  stage-swap mutants exited 2 (wrong-stage counter raised as a setup error),
  which the frozen rule does not count as kills. `raw/iter1-59ff5811/`.
- **Iteration 2 (`3eee0a4b`, test-only change): PASS.**
  - `ExperimentCcfDcStage`: CPU build G1–G5 440/26/96/240/32 pass, 0 fail;
    CUDA build 1100/65/240/600/80 pass, 0 fail, 0 inconclusive.
  - Restoring mutants 10/10 killed with exit 1 (`cpu_restore`, `cpu_wrong_bin`,
    `cpu_stage_swap` on both builds; `cuda_single_restore`,
    `cuda_batched_restore`, `cuda_single_resident`, `cuda_single_stage_swap`).
  - Fail-closed: arm unset or `Both` aborts with exit 134 and no MRC/STAR, CPU
    and CUDA (4/4).
  - Existing focused tests under every arm (CudaPatchBatch, CudaHermitianCCF,
    CudaPeakFit, PatchRetryState CUDA and CPU): 20/20 exit 0.
  - GPU2 UUID `GPU-063e5232-...598` idle before and after, ECC 0.
- Stage characterization (numerical reference, not a motion oracle): the
  conditioned stage's fitted-shift error vs the long-double same-CCF reference
  is ≤7.7e-6 px at every pedestal on all five paths. Unconditioned error is
  ≤7.7e-6 px at pedestal 0; at DC/contrast 81 the worst case is already
  1.2–1.7 px (an integer peak change), and at 5.3e6 every case errs by
  ≥1.4e-3 px (worst 7.5 px). A NaN in a frame's DC bin gives a silent zero shift
  reported as converged when unconditioned, and is masked when conditioned; a
  NaN in a non-DC bin gives a silent zero shift in every arm. Flat, tie and
  boundary cases are characterization only. `raw/iter*/phase0-build.tar.gz`.

## Tier A — `motion-diagnostics/2` (complete)

80 native processes (8 cases × CPU/CUDA × none/global/local/both/plain), all
exit 0. Fixtures are byte-identical to #273's. Per arm, over both backends, the
unchanged checker gives **2 PASS / 10 FAIL / 4 UNIDENTIFIABLE**, the same as
#273; every nonzero case still FAILs its field gate in every arm.
Experiment `none` reproduces #273's `d751ff28` products byte-for-byte (MRC core
header, payload, movie STAR) in 16/16 runs.

Field RMS px, CPU / CUDA ([full table](results/tables.md)):

| case | none | global | local | both |
|---|---|---|---|---|
| integer | 0.298 / 0.285 | **0.587 / 0.453** | 0.298 / 0.285 | **0.587 / 0.453** |
| fractional | 0.592 / 0.379 | 0.369 / 0.369 | 0.592 / 0.379 | 0.369 / 0.369 |
| affine | 0.455 / 0.323 | 0.343 / **0.822** | 0.501 / 0.308 | 0.362 / 0.362 |
| pedestal | 2.394 / 2.394 | 0.465 / 0.465 | 0.693 / 0.693 | 0.361 / 0.362 |
| noisy | 2.647 / 2.978 | 1.971 / 1.984 | 2.626 / 1.835 | 1.885 / 1.885 |

Retained regressions: global conditioning worsens integer on both backends and
makes CUDA integer globally nonconverged; CUDA global-only worsens affine.
The latest W4 review attributes the simple-case failures to a production
weight / rotated-peak estimator / iteration interaction (scope five frames);
the pedestal case has an active local model in 1/9 patches. That attribution
is W4's and is not adopted or retested here.

Controls (plain vs experiment `none`): MRC core header, payload and movie STAR
are raw-byte identical in 16/16; the index `corrected_micrographs.star` differs
only by the run-directory path, so the rule-r2 status is
**DIFFERENT_PATH_ONLY** in 16/16 (`raw/.../eval/controls-r2-tierA.json`, raw
diffs and normalization scope included). Provenance: the original evaluator
(`b20bff53`) reported 16/16 DIFFERENT; its `controls.json` was overwritten at
19:34:44Z by an interim evaluator (`abd1aec1`) that labelled path-only
equivalence IDENTICAL. That interim file is kept unchanged
(`eval/controls.json`, `5da1f914`); the original rule was replayed by the
pinned script into `eval-replay-original-rule/` (labelled REPLAY, 16/16
DIFFERENT). All three scripts are in `tools/`.

## Tier B — `motion-counting/1` (in progress)

Snapshot: CUDA 264/402 and CPU 122/402 processes exit 0, 345 evaluated, no
nonzero exit or admission failure. Complete paired cells (10 seeds, both
backends): pedestal32 and pedestal0; CUDA also contrast025, contrast4, dose1,
dose05. All other cells are IN_PROGRESS or UNRUN in
[tables.md](results/tables.md); categories are only assigned at 10/10 pairs.

- **Pedestal 32:** `both` improves field RMS 10/10 on each backend (median
  1.788 → 0.299 px CPU, 1.738 → 0.299 px CUDA; sign p = 0.00195), worst max
  6.54 → 1.56 px, in-band transfer 0.926 → 0.991 and top band 0.659 → 0.954.
  Global-only and local-only each improve partially. Global nonconvergence is
  10/10 with none/local and 0/10 with global/both; local model disabled 10/10
  with none/global. Field-distance FAIL (unchanged 0.20/0.40/0.80 Å) remains
  9/10 with `both`, 10/10 otherwise. Global-only has higher in-band transfer
  (0.994) than `both` (0.991) despite field RMS 0.894 px; retained as is.
- **Pedestal 0:** all arms equal within ~1e-7 px (neutral/mixed).
- CUDA contrast025/contrast4/dose1/dose05: neutral/mixed on field RMS; two
  nominal transfer improvements of ≤6e-5. Every per-seed regression is listed
  in `results/tierB.json` and `tables.md`.

This replicates #269's pedestal-32 direction on the new exact source. It is a
counting-texture proxy, not downstream science.

## Tier C — compatibility diagnostic

UNRUN (816 processes queued after Tier B on each backend).

## Cost

UNRUN. Correctness wall times are unqualified. The prepared protocol in
FREEZE.md needs bounded ≤45 min benchmark windows, run as several windows, not
one exclusive reservation.

## M3 options (no recommendation yet)

none / global / local / both, decided by the maintainer after Tier B and Tier C
complete and an independent review. Current evidence: `both` is the only arm
that removes the pedestal-driven truth failure on both backends; global-only
introduces Tier A regressions on integer (both backends) and CUDA affine; no
arm makes any nonzero Tier A case pass its field gate.

See [HANDOFF.md](HANDOFF.md) for live-job ownership and commands.
