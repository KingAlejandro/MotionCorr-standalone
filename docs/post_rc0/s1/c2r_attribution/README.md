# S1.3c: how much of S1 is the cuFFT C2R row term h(y)?

Post-RC0 S1 campaign ([#238](https://github.com/KingAlejandro/MotionCorr-standalone/issues/238)), follow-up to the C2R finding in [#253](https://github.com/KingAlejandro/MotionCorr-standalone/issues/253) and PR #250 (S1.3/S1.3b). Frozen source F = `6d68e2d6`. Diagnosis only: no product source, gate or default was changed, and no timing claim is made. Relative RMSE is the `compare_motioncorr.py --gate backend` value, recorded only (Tier B); "S1" means relative RMSE ≥0.1, the #243 screen.

## Result

**h(y) explains about half of S1 on 4096² movies. Removing it takes the screen-positive 4096² configurations from 27 to 15: 13 disappear, 1 new one appears, 14 remain.** Measured on all 19 screen-positive 4096² movies of #243, both grids.

**What remains is the S1.3 near-tie mechanism, now driven only by global-trajectory differences, plus one global-alignment failure.** With h(y) removed:
- **12963 5×5:** CPU and CUDA global trajectories still differ by 0.03 px, and that alone reproduces S1 (relative RMSE 0.316). Two S1-relevant patches flip at 1–3-ulp near-ties.
- **Equal trajectories and h(y) removed:** CUDA patch inputs match CPU to ≤5.9e-7, and no S1-relevant patch remains in 10216 5×5 or 12963 5×5.
- **The 15 positive configurations after the toggle (14 kept, 1 created):**
  - 13 have CPU/CUDA global trajectories 0.018–0.30 px apart.
  - The other two are 10216-01 (both grids): its global alignment does not converge, the trajectories end 177 px apart, and the toggle cannot change it.

**Removing h(y) is not monotone.** The near-tie lottery is reshuffled rather than only thinned: 10216-07 5×5 goes 0.037 → 0.995 (new S1), and 12963-01 5×5 goes 0.147 → 0.828.

**Non-4096 control:** on 10641 (5760×4092) cuFFT does not leak, the toggle is rounding-level (1.9e-8 on the real frames), and both 10641 5×5 positives stay S1-positive with unchanged relative RMSE (0.8078, 0.8794).

**Products:** h(y) is a small part of the global-only CPU/CUDA level in the two 4096² movies tested. With the DW projection, the DW micrograph moves 0.0166 → 0.0165 (10216-00) and 0.0227 → 0.0209 (12963-00). It is a large part in 10028 under config L: 0.014–0.034 → 0.005–0.015 with both projections, a 34–76% reduction.

### Per family (CPU vs CUDA; toggle off → global + DW projection on)

| family (frame size) | movies | 5×5 S1 | 3×3 S1 | change |
|---|---:|---|---|---|
| 10216 (4096²) | 8 | 7 → 5 | 5 → 2 | 6 removed, 1 created (07 5×5) |
| 12963 (4096²) | 7 | 7 → 6 | 3 → 1 | 3 removed |
| Falcon 3 (4096²) | 4 | 4 → 1 | 1 → 0 | 4 removed |
| 10028 (4096², negative control) | 3 | 0 → 0 | 0 → 0 | relative RMSE 0.014–0.034 → 0.005–0.015 |
| Falcon 4 (4096², negative control) | 2 | 0 → 0 | 0 → 0 | 0.021–0.027 → 0.014–0.019 |
| 10641 (5760×4092, non-4096 control) | 2 | 2 → 2 | 0 → 0 | unchanged |

Incidence here is over the movies run, which were #243's screen-positive 4096² movies plus the controls. The other 11 movies of these three 4096² families were not rerun. Since the toggle created one positive among the 11 screen-negative configurations of positive movies, the after-toggle incidence for whole families is not established.

### Per configuration

"acc." is patches kept CPU / CUDA; * marks differing accepted sets.

| venue | movie | grid | off | global | global+DW | acc. off → global+DW | S1 |
|---|---|---|---:|---:|---:|---|---|
| 4GPUs | 10216-00 | 5×5 | 0.4344 | 0.0175 | 0.0173 | 21/20* → 21/21 | gone |
| 4GPUs | 10216-00 | 3×3 | 0.1962 | 0.1828 | 0.1828 | 9/9 → 9/9 | kept |
| 4GPUs | 10216-01 | 5×5 / 3×3 | 1.2485 | 1.2485 | 1.2485 | 0/0 → 0/0 | kept (global alignment fails) |
| 4GPUs | 10216-02 | 5×5 | 0.3278 | 0.0213 | 0.0211 | 19/19* → 19/19 | gone |
| 4GPUs | 10216-03 | 5×5 | 1.2569 | 0.2407 | 0.2407 | 6/8* → 6/6 | kept |
| 4GPUs | 10216-06 | 5×5 | 0.4831 | 0.0534 | 0.0532 | 12/11* → 12/12 | gone |
| SCARF | 10216-07 | 5×5 | 0.0371 | 0.9951 | 0.9951 | 11/11 → 11/12* | **created** |
| SCARF | 10216-07 | 3×3 | 0.7270 | 0.0887 | 0.0886 | 8/9* → 8/8 | gone |
| SCARF | 10216-08 | 5×5 | 0.2441 | 1.0452 | 1.0452 | 9/9 → 9/9* | kept |
| SCARF | 10216-08 | 3×3 | 0.9902 | 0.0539 | 0.0539 | 8/9* → 8/8 | gone |
| SCARF | 10216-09 | 5×5 | 0.9123 | 0.9129 | 0.9129 | 10/11* → 10/11* | kept |
| SCARF | 10216-09 | 3×3 | 0.1135 | 0.0985 | 0.0984 | 8/8 → 8/8 | gone |
| 4GPUs | 12963-00 | 5×5 | 0.4990 | 0.3156 | 0.3155 | 22/23* → 22/23* | kept |
| 4GPUs | 12963-01 | 5×5 | 0.1469 | 0.8279 | 0.8278 | 5/5 → 5/6* | kept |
| 4GPUs | 12963-02 | 5×5 | 0.4618 | 0.0527 | 0.0517 | 19/19* → 19/19 | gone |
| 4GPUs | 12963-03 | 5×5 | 0.7326 | 0.6619 | 0.6618 | 11/11* → 11/11* | kept |
| 4GPUs | 12963-03 | 3×3 | 0.1188 | 0.0731 | 0.0720 | 9/9 → 9/9 | gone |
| 4GPUs | 12963-04 | 5×5 | 1.0028 | 0.3729 | 0.3727 | 10/8* → 10/10 | kept |
| 4GPUs | 12963-04 | 3×3 | 0.3048 | 0.0967 | 0.0962 | 9/9 → 9/9 | gone |
| 4GPUs | 12963-05 | 5×5 | 0.3895 | 0.1311 | 0.1309 | 4/4 → 4/4 | kept |
| 4GPUs | 12963-05 | 3×3 | 0.2876 | 0.2549 | 0.2548 | 5/5 → 5/5 | kept |
| 4GPUs | 12963-07 | 5×5 | 0.2745 | 0.1784 | 0.1780 | 19/21* → 19/20* | kept |
| 4GPUs | Falcon 3-00 | 5×5 | 0.5999 | 0.5941 | 0.5940 | 20/21* → 20/21* | kept |
| 4GPUs | Falcon 3-02 | 5×5 / 3×3 | 0.1603 / 0.1016 | 0.0218 / 0.0224 | 0.0189 / 0.0195 | 25/25, 9/9 | gone |
| 4GPUs | Falcon 3-03 | 5×5 | 0.2911 | 0.0213 | 0.0187 | 25/25 → 25/25 | gone |
| SCARF | Falcon 3-04 | 5×5 | 0.2734 | 0.0316 | 0.0300 | 25/25 → 25/25 | gone |
| 4GPUs | 10641-01 | 5×5 | 0.8078 | 0.8078 | 0.8078 | 8/9* → 8/9* | kept (non-4096) |
| 4GPUs | 10641-07 | 5×5 | 0.8794 | 0.8794 | 0.8794 | 7/7* → 7/7* | kept (non-4096) |

Negative grids of positive movies and the 10028/Falcon 4/10641 3×3 rows are in [`raw/attribution_all.json`](raw/attribution_all.json). None turned positive except 10216-07 5×5. The S1 cases that remain with the projection on have global-trajectory differences listed in [`raw/remaining_s1_global_traj_diff.json`](raw/remaining_s1_global_traj_diff.json).

## Part 2: equal trajectories with h(y) removed (S1.3 inputs, 5×5)

CUDA ran with the global projection on, (a) with CPU's global trajectory injected and (b) with its own. It was compared against the S1.3b CPU own-trajectory run (iteration-1 patch inputs; per-frame records; `raw/4gpus/analysis/`; per-run records are in `raw/4gpus/runs.tar.gz`).

| | 10216 | 12963 |
|---|---|---|
| patch-input difference, projection on + CPU trajectory | median 5.0e-7, max 5.9e-7 (1475 patch-frames) | median 2.4e-7, max 3.5e-7 (975) |
| same, projection off (S1.3b) | median 1.6e-3, 100% in kx = 0 | median 6.1e-3, 100% in kx = 0 |
| (a) equal trajectory: relative RMSE; S1-relevant patches; first-separation events | 0.0148; 0 / 1 before; 3 near-ties ≤2 ulps | 0.0343; 0 / 5 before; 10 near-ties ≤6 ulps |
| (b) own trajectory: relative RMSE; S1-relevant patches | 0.0175; 0 | **0.3156; 2**: (1,1) adjacent 2/1-ulp near-tie at frame 31 (5.3 px jump, 1.9 px final); (5,1) acceptance flip from a 3/1-ulp near-tie |

So with the inputs equal to rounding, the near-tie events that remain come from CCF arithmetic rounding (≤9 ulps, S1.3) and do not reach S1 here. The global-trajectory difference (0.03 px in 12963) is enough to bring S1 back.

## Part 4: products (config G with `--save_noDW`, 4GPUs)

Relative RMSE CPU vs CUDA (`raw/4gpus/analysis/part4.txt`):

| movie | arm | DW micrograph | non-DW micrograph |
|---|---|---:|---:|
| 10216-00 | off | 0.01659 | 0.01964 |
| | global projection | 0.01659 | 0.01939 |
| | DW projection | 0.01646 | 0.01964 |
| | both | 0.01646 | 0.01939 |
| 12963-00 | off | 0.02273 | 0.03298 |
| | global projection | 0.02273 | 0.03094 |
| | DW projection | 0.02088 | 0.03298 |
| | both | 0.02088 | 0.03094 |

h(y) reaches both published sums, but in these two movies it is ≤8% of the global-only CPU/CUDA level (≤1.3% for 10216). The rest of the ~0.017–0.023 is not h(y) and was not decomposed here. In the 10028 controls (config L) both projections lower the DW-micrograph relative RMSE by 34–76%, so the share varies by family.

## Method

Diagnostic commit `1c82dfcd` on the unmerged branch `diag/s1-ccf-ties` ([`diag_s1_3c_c2r_hermitian.diff`](diag_s1_3c_c2r_hermitian.diff)) adds two env toggles. Each applies the #253 projection F(ky) ← (F(ky) + conj F(−ky))/2 to the kx = 0 and kx = nx/2 columns of the half spectrum, on the copy fed to cuFFT:
- `MC_DIAG_C2R_HERMITIAN_GLOBAL=1` before the global inverse C2R (`computeGlobalInverseFFT`);
- `MC_DIAG_C2R_HERMITIAN_DW=1` before the DW product C2R (`cuda_realspace_dw.cu`).

`cuda_fft_prep.cu` (the non-resident path) is not toggled; these runs use the resident session (`--ingest auto`).

- **Part 3 replay.** Each CUDA arm replays the exact argv and cwd of the matching #243 sweep run (`tools/run_c.py`), changing only the binary, the output paths, the GPU lane and the env. The CPU reference is the sweep's frozen-F CPU product on the same host: QF build `43cab2b7…`, 4GPUs. On SCARF the CPU arm was rerun with the sweep's `build-F-cpu` (`ca1bb8f9…`) on the same node as the CUDA arms, after re-downloading the four movies from EBI with SHA-256 checks and rebuilding `movies.star` byte-identical to the sweep's recorded hashes.
- **Neutrality.**
  - With the toggle off, all 44 4GPUs arms are byte-identical to the sweep's CUDA products (MRC core header, payload and STAR; `off_identical_to_sweep_cuda` in `raw/4gpus/analysis/attribution_4gpus.json`).
  - On SCARF the sweep's products were not retained, so the check is that all 8 toggle-off arms reproduce the sweep's recorded relative RMSE to every printed digit.
- **Size control.** 10641-01 full-frame dumps (`tools/campaign_f.sh`, `tools/sizectl.py`). CUDA real frames match a float64 `irfft2` of the spectrum to 3.0e-7, with no row term (row-mean rms 5.6e-8 of the frame rms). The projection changes the real frames by 1.9e-8. The toggle is therefore rounding-level at 5760×4092, not byte-identical, and can still move near-tie outcomes: 10641-07 3×3 goes 0.0229 → 0.0253.
- **Runs.** 4GPUs: 132 part-3 arms, 14 part-2/4 runs and 2 size-control runs, all exit 0. Lane GPU2 `GPU-063e5232-…` with its per-GPU lock, CPUs 112–119, every CUDA run UUID-witnessed. The bench lock was probed in shared mode, because the #253 agent held it shared for correctness work. SCARF: job 3646472 on gn0003 (A100-SXM4-40GB, driver 580.178.04, 8 CPUs), 32 runs, all exit 0, diag4 build `43f61daf…`. Builds: 4GPUs diag4 CUDA+nvCOMP `441097ea…`, both Release `-O3 -DNDEBUG` (`raw/4gpus/build-info.txt`, `raw/scarf/build.status`). Per-run records (run.json with argv, env, binary hash, exit status and GPU witness; per-movie STAR and log; per-frame CCF records for part 2) are in `raw/4gpus/runs.tar.gz` and `raw/scarf/runs.tar.gz`.
- **Tools.** In `tools/`: `run_c.py`, `campaign_d.sh` (part 3), `campaign_e.sh`/`post_e.sh`/`part2.py` (parts 2 and 4), `campaign_f.sh`/`sizectl.py` (size control), `analyze_c.py`, `gtraj.py`, and the SCARF scripts. `analyze.py`, `pairs.py`, `summarize.py`, `counts.py`, `identity.py` and `run.py` are copies of PR #250's tools at `7fc9733f`; `run.py` has the shared bench probe.

## Open

- **After-toggle incidence for whole families.** The 11 screen-negative movies of 10216, 12963 and Falcon 3 were not rerun, and the toggle can create positives.
- **Why the remaining global trajectories differ by up to 0.30 px.** S1.3 traced ≤0.045 px to rounding. Larger differences (12963-04 0.15 px, 10216-09 0.30 px) were not analysed.
- **10216-01's global-alignment failure** on both backends: diagnosed only to "non-converging, trajectories 177 px apart".
- **The rest of the global-only product difference** (~0.017–0.023 without h(y)) is not decomposed.
- **S1.4** (downstream CTF/FSC/B-factor) still decides whether any of this matters. The #253 product fix is separate work.
