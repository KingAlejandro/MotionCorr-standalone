# #264 N3/N4 CPU subset (cpu1): frozen plan, not launched

Status: **proposal frozen 22 October 2026, no build or native run**. It needs parent verification
and a new independent review first. This area is new. The iteration-1 campaign (`../FROZEN.md`,
`0a1f64ab`), its predictions and raw outcomes, and the full iteration-2 proposal
(`../n3-iter2/`, from `521fddae`) are unchanged.

## Why a CPU subset

The original chain ended at `n2-gpu`. Pre-health saw foreign PID 3276184 on GPU1, so it exited 3 before
any GPU arm. N1 CPU/CUDA/nvCOMP and N2 CPU passed (parent readbacks in `../parent-verification/`).
N3/N4 never started, and all four GPUs are currently blocked. This subset runs the 24 CPU rows of N3/N4
(3 CPU arms × 7 cases plus the no-overlay row) through the real runner. The 16 CUDA rows stay
**UNRUN**. A CPU-subset PASS does not complete N3/N4 and is not CPU+CUDA qualification.

## Bindings (checked by `check_sources.py` before any build; mismatch stops the chain)

- **Candidate:** the commit adding this file. Its `src`, `tests`, `tools` and `CMakeLists.txt` equal `52affe31`, and `src` equals `4b0e4e73` (git trees `edd1737d…` for `src`). Base is `3691374061f782bc84531fd1c79d017ddcb5a7c2`.
- **Tree hashes:** each tree's runner/helper/diff hashes must equal the iteration-1 `SOURCES.txt` values (`iteration1_SOURCES.txt`):
  - `src-ov-base` runner `70fc2de0…`;
  - `src-ov-cand` runner `55423793…`, helper `02d8f5c1…`;
  - `src-ov-mut` runner `55423793…`, uncentred helper `d531871f…`.
- **Predictions:** `n3-iter2/predictions_iter2.json` sha256 `6ff11cb5145f3c9f3f0c6380de26b27913eb9da7ccb6652a783c777b205c859e` (R3-reviewed; A totals 3.5). `n3_cpu1.py` refuses any other file.
- **Unchanged tooling:** overlay patch `f82196ac…4249`; original `tools/n3.py` `68dcf292…7ba3f`, `runlib.py` `faa27bfa…5454`, `build.sh` `e51a7cee…b664`.
- **Fixture:** `km_local_nonsquare.mrcs` sha256 `644274e0…3fb3`, read in place (asserted by `n3.run`).
- **Binaries:** recorded at build in `build-ov-*-cpu.binaries.sha256`. No overlay binary exists yet, so no expected hash is claimed.

## Lane and stages (`chain_cpu1.sh`)

- **Host:** 4-gpu-vm, CPUs 14–15 only (chain run under `taskset -c 14-15`), builds `--parallel 2`, runtime `--j 1` with one numeric thread.
- **Locks:** CPU lease `/tmp/motioncorr-guard264-cpu14-15.lock` held for the whole chain; it stops if `/tmp/motioncorr-i61-cpu-14-15.lock` is held. Build lock is nonblocking (exit 5 on contention).
- **No GPU:** no `nvidia-smi`, CUDA configure, GPU lock or GPU run. `occupancy_cpu.sh` uses `/proc/stat` and fails if CPUs 14–15 are more than 50% busy or the scratch exceeds 8 GiB.
- **Scratch:** a new `/mnt/clathrin/alex-motioncorr-guard264-20261022-<sha12>-cpu1`, prepared by the unchanged `../tools/setup.sh` from a bundle of this commit.
- **Stages, each new and never retried:**
  1. `cpu1-occupancy-start`
  2. `cpu1-sources`
  3. `cpu1-b-ov-base-cpu`, `cpu1-b-ov-cand-cpu`, `cpu1-b-ov-mut-cpu` (CPU Release, target `motioncorr`, `MC_REQUIRE_ALL_DECODERS=ON` with the pinned pbzip2)
  4. `cpu1-receipts`
  5. `cpu1-n3-cpu`
  6. `cpu1-grade`
  7. `cpu1-occupancy-end`
- **Stop rule:** the first nonzero stage stops the chain. A later attempt is a new scratch and a new record.

`cpu1-receipts` writes `n3-cpu1/known-observations.json` before any run: per row the exact
`MC264_N3_COEFFS` string, its sha256, the rational coefficients and the predicted outcome.
`run cpu` refuses when the receipts are missing or differ. The per-observation values exist only
inside the runner. The overlay line witnesses n_obs/nx/ny/n_frames, and published coefficients witness
accepted models.

## Expected outcomes (iteration-2 predictions, unchanged tolerances)

| Case | ov-base-cpu (legacy) | ov-cand-cpu (finite) | ov-mut-cpu (uncentred) | base/cand images |
| --- | --- | --- | --- | --- |
| A_x | accept, model published | reject 3.181818 (z10) | accept, model published | differ |
| B_x | reject 3.282981 (z8) | accept, model published | reject 3.276145 (z8) | differ |
| A_y | accept, model published | reject 3.181818 (z10) | accept, model published | differ |
| B_y | reject 3.288128 (z8) | accept, model published | reject 3.277861 (z8) | differ |
| E_xy | reject 3.240000 (z6) | accept, model published | reject 3.235781 (z6) | differ |
| F | accept, model published | accept, model published | accept, model published | equal |
| G | reject 5.454545 (z2) | reject 5.454545 (z2) | reject 5.454545 (z2) | equal |
| Z_no_overlay | no overlay line; guard/STAR consistent (no frozen decision) | same | same | equal |

**Per row (original `n3.grade`, unchanged):**
- rc 0;
- no CUDA activity;
- exactly one overlay line (768/512/12, n_obs > 18), and none on Z;
- guard line present iff reject, with the printed delta within 2e-5 relative;
- STAR local model present iff accept, with coefficients within 1e-5 of the injected values.

**Pairs:** the base/cand global-shift block is identical, and images are equal iff decisions agree.

**CPU-subset verdict** (`CPU_SUBSET.json`):
- the original grade lists 24 CPU rows PASS and the 16 CUDA rows UNRUN, and exits 1 because of them;
- 8 CPU pairs PASS and no CUDA pair;
- no CUDA arm directory;
- N4 PASS, with the mutant differing from the candidate on exactly A_x, A_y, B_x, B_y and E.

The report states `full_n3_n4_aggregate: INCOMPLETE: 16 CUDA rows UNRUN`. The original
`RESULTS.json` is kept as written by the unchanged grader.

## Host mock controls (`test_cpu1_controls.py`, run before freezing; 22/22 as intended)

- **Positive:** 24 synthesised CPU rows give a subset PASS and an INCOMPLETE aggregate.
- **Negatives:** each one gives exit 1 with the named problem:
  - missing row;
  - wrong-case content;
  - the old 3.3 printed value for candidate A;
  - absent overlay line;
  - overlay on the Z row;
  - STAR model on a reject row;
  - STAR model missing on an accept row;
  - mutant behaving like the candidate (N4);
  - CUDA marker in a CPU arm;
  - nonzero rc;
  - missing MRC (the original grader raises, so the subset fails closed);
  - pair image mismatch;
  - a CUDA arm present;
  - a modified predictions file (refused by hash).
- **Receipts:** written for 24 rows, 21 of them with an overlay; overwrite is refused; `run gpu` is refused; tampered receipts are refused before any run; no run directory is created.
- **Sources:** iteration-1 `SOURCES.txt` passes; one altered helper hash is rejected.

## Limits

These are test-only overlay builds. Injected observations exercise the fit, guard, fallback,
reconstruction and STAR wiring on a known model. They do not show whether real CCF observations are
accurate. The CUDA rows and the CUDA mutant are UNRUN. N2 GPU remains UNRUN. No timing,
accuracy or science claim. F3 (non-finite models) and F4 (maintainer parity sign-off) are carried.
