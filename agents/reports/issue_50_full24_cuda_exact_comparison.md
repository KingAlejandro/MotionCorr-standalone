# MotionCorr PR #51 full 24 movie comparison

## Result

The optimized build and a fresh PR #51 baseline build both completed all 24 tutorial movies on GPU 1 with exit status 0. Each used `--use_own --j 4 --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1`; both ran from `/home/alex/MotionCorr-standalone/relion30_tutorial` and read the same `movies.star` (SHA256 `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041`) and gain reference (SHA256 `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`).

All 24 corrected MRCs were pixel-identical. Across all movie STARs, normalized STAR fields had zero differences and every per-frame trajectory matched exactly. Worst absolute pixel error, image RMSE, relative image RMSE, trajectory coordinate error, and STAR-field difference count were all zero. No per-movie mismatches.

The root `corrected_micrographs.star` also had zero normalized field differences. Its format has no per-frame shifts; trajectory parity is established from the 24 per-movie STAR files.

## Provenance

- Optimized source: production SHA `5352d4d` (provided for this run); CUDA binary `/home/alex/MotionCorr-issue50-opt-test/build-cuda/motioncorr`, SHA256 `ecead19357554807f203b358cfae8fb9f17e0823a4d935e891e5c40eab71c576`.
- Baseline source: clean tracked checkout HEAD `08236c2208b10c7caf93ecf83676ddb97c58fca3`. A new CUDA build was produced in `/home/alex/MotionCorr-issue50-review-v2/build-parity-08236c2` using Release, `CUDA=ON`, `TIMING=ON`, and CUDA architecture 80. Binary SHA256 `6ec086e00e47e9133f0f8367caecb7f5c0bf6873cb758c513bb3609c0c45c54b`.
- The older baseline binaries were not used because their build-time source SHA was not recorded and their timestamps predate the checkout HEAD commit.

## Runtime and memory observations

- Optimized: 64.45 s wall time; 104.13 s user CPU; max host RSS 1,648,860 KiB.
- Fresh baseline: 104.90 s wall time; 257.07 s user CPU; max host RSS 1,646,736 KiB.
- Both used GPU 1. A live `nvidia-smi` spot sample during each run showed about 435 MiB GPU memory in use; this is not a measured peak. Since this was one run per binary, timings are recorded without a speed claim.

## Artifacts

- Optimized output and run log: `/home/alex/MotionCorr-issue50-opt-full24-check/opt-20260924a/`
- Baseline output and run log: `/home/alex/MotionCorr-issue50-opt-full24-check/base-08236c2/`
- Per-movie detailed comparisons: `/home/alex/MotionCorr-issue50-opt-full24-check/per-movie-comparison.json`
- Comparison script: `/home/alex/MotionCorr-issue50-opt-test/tools/compare_motioncorr.py` (run with `/home/alex/mc-env/bin/python`, exact gate)
- Build and configure logs: `/home/alex/MotionCorr-issue50-opt-full24-check/build-baseline.log` and `configure-baseline.log`
