# Metal validation on one real RELION tutorial movie (2026-09-24)

## Outcome

The M4 Pro Metal build completed a real 24-frame RELION tutorial movie in 5×5 patch mode with dose weighting and wrote corrected MRC and STAR outputs. The relaxed Gate 2 comparison **fails**: trajectory and STAR checks pass, but relative corrected-image RMSE is about 0.01322–0.01323 against the unchanged 0.001 limit. This is not an overall parity pass.

Two timed runs per backend give medians of 29.37 s CPU and 28.30 s Metal (apparent 1.04× CPU/Metal ratio). This is too small a sample to establish a reliable end-to-end speedup; the required three steady-state runs have not been completed. The earlier 13.6× full-pipeline figure in the feasibility note remains a projection and is not supported by this real-movie result.

## Provenance and reproduction

- Source revision tested: `637b8117c83c670b6556ee6ef31a594ed6f78494` (`feat/issue-35-metal-patch-feasibility`).
- Hardware/software: Apple M4 Pro, macOS 26.6.2, arm64; the same optimized Release (`-O3`) `METAL=ON` executable was used for both backends.
- Dataset: RELION tutorial movie `20170629_00021_frameImage.tiff`, 24 frames, 3710×3838, 16-bit, 126,550,106 bytes. SHA-256: `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`.
- Gain reference SHA-256: `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`.
- RELION tutorial data archive: `ftp://ftp.mrc-lmb.cam.ac.uk/pub/scheres/relion30_tutorial_data.tar`; the tutorial describes this archive [here](https://relion.readthedocs.io/en/release-4.0/SPA_tutorial/Introduction.html).
- Shared run options: `--use_own --j 1 --seed 1 --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc`. CPU runs omitted `--metal`; Metal runs enabled it and selected device 0 (Apple M4 Pro).
- Four runs exited successfully and produced corrected MRC and STAR files. Ghostscript was not installed, so RELION's optional PDF log assembly emitted errors/empty PDFs; this did not prevent MRC/STAR production or comparison.

The 128 MB movie and 57 MB gain file are intentionally not checked into Git. Input hashes above identify the public tutorial assets. Output hashes are recorded in the JSON evidence alongside this report.

## End-to-end timing

| Backend | Run 1 | Run 2 | Two-run median |
| --- | ---: | ---: | ---: |
| CPU | 29.64 s | 29.10 s | 29.37 s |
| Metal | 29.94 s | 26.66 s | 28.30 s |

The ratio of these two medians is 1.04×. Runs were not thermally randomized and there were only two observations per backend; treat this as exploratory, not a performance acceptance result.

## Relaxed Gate 2 comparison

| Check | Gate limit | CPU/Metal pair 1 | CPU/Metal pair 2 | Result |
| --- | ---: | ---: | ---: | --- |
| Coordinate RMS shift error | ≤0.020 px | 0.009913 px | 0.009913 px | PASS |
| Maximum shift error | ≤0.050 px | 0.015351 px | 0.015351 px | PASS |
| Corrected-image RMSE | ≤0.020 | 0.0106666 | 0.0106574 | PASS |
| Relative corrected-image RMSE | ≤0.001 | 0.0132319 | 0.0132205 | **FAIL** |
| Maximum pixel error | ≤5.0 | 2.27237 | 2.27237 | PASS |
| Normalized STAR differences | 0 | 0 | 0 | PASS |
| Overall | Every required check passes | **FAIL** | **FAIL** | **FAIL** |

No threshold was changed. The relative image-RMSE failure is roughly 13.2× the limit. The MRC pixel arrays are not identical. Normalized STAR output agrees; volatile/core-header differences are not treated as STAR differences.

## Profile observations

The CPU logs report global alignment at 0.736 s and 0.779 s, with real-space interpolation at 1.475 s and 1.643 s. On the second Metal run, the backend reported 976.41 ms total global alignment (381.90 ms host-to-device, 149.24 ms custom kernels, 288.78 ms MPSGraph FFT, 147.53 ms device-to-host), with 1482.91 MiB peak Metal allocation. Its full-movie real-space interpolation stage was 1.438 s, with the resampling kernel reporting 0.9898 s. Metal global alignment therefore did not beat the CPU alignment time in these two observations; other CPU-heavy FFT and dose-weighting stages remain in the full pipeline.

## Component probe: scope and result

`tests/metal_resample_probe.mm` and `docs/metal_resample_probe_20260924.log` preserve the synthetic resampling experiment. The 2048×2048×16 case measured 250.46 ms CPU versus 112.22 ms Metal dispatch (2.23× for this one component case); uniform-weight, dose-weighted, edge-clamping, and high-resolution component parity checks passed their probe limits. This does **not** evaluate full-motion Gate 2, fitted trajectories, the whole movie path, or end-to-end performance. The probe was manually compiled against the existing Metal-enabled Release static library and linked with Apple's Foundation/Metal frameworks; it is not yet a project build target.

## Acceptance still outstanding

This evidence covers only one real 5×5, dose-weighted movie. It does not cover 3×3 patches, an unweighted run, the 24-movie set, or three steady-state timing repeats. Issue #35 should remain open; Issue #32's all-checks Gate 2 and timing criteria also remain unmet. Keep the probe result labeled component-only.
