# S1.3c: how much of S1 is the cuFFT C2R row term h(y)?

Post-RC0 S1 campaign ([#238](https://github.com/KingAlejandro/MotionCorr-standalone/issues/238)), follow-up to the C2R finding in [#253](https://github.com/KingAlejandro/MotionCorr-standalone/issues/253) and PR #250 (S1.3/S1.3b). Frozen source F = `6d68e2d6`. Diagnosis only: no product source, gate or default was changed, and no timing claim is made. Relative RMSE is the `compare_motioncorr.py --gate backend` value, recorded only (Tier B); "S1" means relative RMSE ≥0.1, the #243 screen.

## Result

**Removing h(y) reduces S1 incidence beyond reshuffling, by about 10 of 60 configurations on the 4096² families: 27 → 17 (−37%).** Measured as a full census of the #243 sample (10 movies each of 10216, 12963 and Falcon 3, both grids, 60 configurations) against the sweep's frozen-F CPU products.
- **Transitions:** 13 configurations go + → − and 3 go − → +. McNemar exact p = 0.021.
- **Size-matched random nulls** move incidence 27 → 27 (3 / 3 discordant, p = 1) and 27 → 29 (3 / 5, p = 0.73). The null adds a random-sign per-row constant with the same rms as each frame's h(y).
- **Directly against the nulls:** #254 has 12 / 2 and 14 / 2 discordant pairs (p = 0.013, 0.004).
- **Per family it is not individually significant:**
  - Falcon 3: 5 → 1 (4 / 0, p = 0.125).
  - 10216: 12 → 7 (6 / 1, p = 0.125).
  - 12963: 10 → 9 (3 / 2, p = 1). Removing h(y) does not lower 12963's incidence.

**#254 (all five CUDA C2R sites) gives the same S1 outcome as the two-site diagnostic toggle in all 60 configurations.** Its products are byte-identical to the toggle's in 41 of the 42 4GPUs configurations. In the one that differs (10216-02 5×5) relative RMSE agrees to four digits (0.0211), and all 18 SCARF values agree to every printed digit. So the two CCF-inverse projections contribute nothing to incidence here.

**On 10641 (5760×4092, no cuFFT leak) #254 takes S1 from 5 → 4 (1 / 0, p = 1).** The null raises 10641's incidence (5 → 9 and 5 → 11). There it adds a perturbation that the frames do not otherwise carry, so it is not a matched null at that size.

**What is left after h(y) is removed** is the S1.3 near-tie mechanism, driven by sub-pixel global-trajectory differences between CPU and CUDA. This is unchanged from the previous revision of this PR:
- With equal trajectories and h(y) removed, CUDA patch inputs match CPU to ≤5.9e-7, and no S1-relevant patch remains (Part 2).
- With 12963's own 0.03 px trajectory difference, S1 returns (0.316).
- 10216-01 (both grids) is a global-alignment failure, with trajectories 177 px apart, and the toggle cannot change it.

**Products:** h(y) is ≤8% of the global-only CPU/CUDA level in 10216-00 and 12963-00 (Part 4).

The earlier "27 → 15" figure came from rerunning screen-positive configurations only. It is superseded: the census shows that the selection was biased (regression to the mean). One created positive (10216-07 5×5) was visible in that sample; the census found 3.

## Census (CPU vs CUDA, 4096² families, both grids)

Off → #254 transitions (stays+, + → −, − → +, stays−) with McNemar exact p. The GLOBAL+DW toggle gives identical tables. The nulls are off → off-plus-random-rows, seeds 1 and 2.

| family | grid | off | #254 | transitions off → #254 | p | null1 (transitions, p) | null2 (transitions, p) |
|---|---|---:|---:|---|---:|---|---|
| 10216 | 5×5 | 7 | 5 | 4, 3, 1, 2 | 0.625 | 7 (6, 1, 1, 2; 1.0) | 8 (7, 0, 1, 2; 1.0) |
| 10216 | 3×3 | 5 | 2 | 2, 3, 0, 5 | 0.25 | 5 (5, 0, 0, 5; 1.0) | 4 (4, 1, 0, 5; 1.0) |
| 12963 | 5×5 | 7 | 7 | 6, 1, 1, 2 | 1.0 | 8 (7, 0, 1, 2; 1.0) | 9 (7, 0, 2, 1; 0.5) |
| 12963 | 3×3 | 3 | 2 | 1, 2, 1, 6 | 1.0 | 4 (3, 0, 1, 6; 1.0) | 5 (3, 0, 2, 5; 0.5) |
| Falcon 3 | 5×5 | 4 | 1 | 1, 3, 0, 6 | 0.25 | 3 (3, 1, 0, 6; 1.0) | 2 (2, 2, 0, 6; 0.5) |
| Falcon 3 | 3×3 | 1 | 0 | 0, 1, 0, 9 | 1.0 | 0 (0, 1, 0, 9; 1.0) | 1 (1, 0, 0, 9; 1.0) |
| **pooled** | 5×5 | 18 | 13 | 11, 7, 2, 10 | 0.18 | 18 (16, 2, 2, 10; 1.0) | 19 (16, 2, 3, 9; 1.0) |
| **pooled** | 3×3 | 9 | 4 | 3, 6, 1, 20 | 0.125 | 9 (8, 1, 1, 20; 1.0) | 10 (8, 1, 2, 19; 1.0) |
| **pooled** | both | 27 | 17 | 14, 13, 3, 30 | **0.021** | 27 (24, 3, 3, 30; 1.0) | 29 (24, 3, 5, 28; 0.73) |
| 10641 (5760×4092) | both | 5 | 4 | 4, 1, 0, 15 | 1.0 | 9 (4, 1, 5, 10; 0.22) | 11 (4, 1, 7, 8; 0.070) |

Per-configuration values for all 80 configurations are in [`raw/census/census_table.md`](raw/census/census_table.md). All tables are in [`raw/census/census_4096.json`](raw/census/census_4096.json) and [`raw/census/census_all.json`](raw/census/census_all.json).

**The null and its validation.** Diagnostic commit `8c8277e8` adds `MC_DIAG_NULL_ROWS=<seed>` ([`diag_s1_3c_null_rows.diff`](diag_s1_3c_null_rows.diff)). After the global inverse C2R and the DW product C2R, it adds σ·s(y) to every pixel of row y:
- s(y) = ±1, hashed from the seed, site, frame and row;
- σ is the rms of that frame's h(y) = −Im(Σ_ky F(nx/2, ky) e^{2πi·ky·y/ny}), computed from the spectrum before the C2R.

On 10216-00 frames 2, 11 and 21 (`raw/census/4gpus/nullcheck.json`), the null's row rms equals h(y)'s rms (0.02393 / 0.14127 / 0.06807 against 0.02393 / 0.14127 / 0.06807). Within-row variation is ~1e-6, and the correlation with h(y) is ≤0.036 in absolute value.

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

**Census arms.** All runs in the census use CPU references from the #243 sweep: the frozen-F product on 4GPUs, or on SCARF the sweep's `build-F-cpu` rerun on the same node as the CUDA arms after re-downloading the movies from EBI with SHA-256 checks. The CUDA arms are:
- off, on (GLOBAL+DW toggle) and null1/null2, from diag5 (`8c8277e8` = `1c82dfcd` + null toggle; 4GPUs `fa3fddcc…`, SCARF `487c7075…`);
- PR #254 head `8b55d5da`, built in a separate tree (Release, CUDA+nvCOMP; 4GPUs `71e226f1…`, SCARF `64c29a8e…`). Its `src` differs from F only by the projection at the five C2R sites.

Neutrality and replay checks:
- **4GPUs:** all 42 diag5 off arms and all 20 10641 off arms are byte-identical to the sweep's CUDA products. All 30 diag5 on arms that overlap with the earlier diag4 runs are byte-identical to them. #254 vs on: 41/42 identical (`raw/census/4gpus/identity_on_vs_pr254.jsonl`).
- **SCARF:** the off arms reproduce the sweep's recorded relative RMSE to every printed digit in both SCARF jobs (18/18 each).

Runs: 4GPUs 292 (lane GPU2 with its lock, CPUs 112–119, UUID-witnessed); SCARF 144 (jobs 3646484 and 3646496, gn0003). All exited 0. Records: `raw/census/4gpus/runs-4gpus.tar.gz`, `raw/census/scarf*/runs.tar.gz`, build info in `raw/census/4gpus/build-info.txt` and `raw/census/scarf*/`. Tools: `campaign_n.sh`, `campaign_p.sh`, `s13n-*`/`s13p-*` SCARF scripts, `census_rows.py`, `census.py` (McNemar exact, two-sided binomial on the discordant pairs) and `nullcheck.py`.

**Earlier S1.3c runs (positive-only sample, parts 2–4).** Diagnostic commit `1c82dfcd` on the unmerged branch `diag/s1-ccf-ties` ([`diag_s1_3c_c2r_hermitian.diff`](diag_s1_3c_c2r_hermitian.diff)) adds two env toggles. Each applies the #253 projection F(ky) ← (F(ky) + conj F(−ky))/2 to the kx = 0 and kx = nx/2 columns of the half spectrum, on the copy fed to cuFFT:
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

- **Per-family significance.** With 20 configurations per family, no single family's change is significant (Falcon 3 and 10216 p = 0.125; 12963 p = 1). Only the pooled 4096² result is (p = 0.021). Two null seeds were run; more would tighten the null band.
- **Why 12963 does not respond** while Falcon 3 and 10216 do. In 12963 the global-trajectory differences alone keep S1 (Part 2) and are larger (up to 0.15 px).
- **Why the remaining global trajectories differ by up to 0.30 px.** S1.3 traced ≤0.045 px to rounding. Larger differences (12963-04 0.15 px, 10216-09 0.30 px) were not analysed.
- **10216-01's global-alignment failure** on both backends: diagnosed only to "non-converging, trajectories 177 px apart".
- **The rest of the global-only product difference** (~0.017–0.023 without h(y)) is not decomposed.
- **S1.4** (downstream CTF/FSC/B-factor) still decides whether any of this matters. The #253 product fix is separate work.
