# Issue #50 optimization validation (24 September 2026)

## Scope and provenance

This addendum measures the implementation based on PR #51 commit `08236c2` with bounded movie FFTs, shared cuFFT workspace, tiled inverse-input preservation, and lazy host gain correction. Production source was built at `5352d4dce6013c49df0220da03b7d4cc0149bdfa`; later commits only modify this report, the design addendum, and the profiling tool. A100 CUDA binary SHA-256: `ecead19357554807f203b358cfae8fb9f17e0823a4d935e891e5c40eab71c576`.

The matched case is tutorial movie `00021` (3710 × 3838 × 24 TIFF frames), gain and dose weighting, 5 × 5 patches, `--j 8 --group_frames 3 --bfactor 150 --angpix 1.06 --dose_per_frame 1.277 --seed 1`, GPU 1 on the 4GPUs A100 host. Normal MRC, STAR, EPS and PDF output remained enabled. The input STAR is `/tmp/issue47-clean-source-bench-20260924/benchmark_input.star`; the movie and gain paths are under `/home/alex/MotionCorr-standalone/relion30_tutorial/Movies/`. Input and binary hashes, benchmark logs, Nsight report, and numerical outputs are retained on that host under `/home/alex/MotionCorr-issue50-opt-performance` and `/home/alex/MotionCorr-issue50-opt-numerical-validation`.

## Measured result

| Metric | PR #51 before this addendum | Optimized | Interpretation |
|---|---:|---:|---|
| Full process wall median, 3 matched runs | 3.80 s | 3.46 s | 8.9% faster; unprofiled runs with normal output |
| Peak sampled whole-device VRAM | 6,033 MiB | 3,537 MiB maximum | 41.4% lower; 47 MiB below the 3,584 MiB target |
| Peak active CUDA allocations in separate Nsight trace | 6,636 MiB | 3,097 MiB | 53.3% lower; excludes CUDA context and untraced driver memory |
| Host peak RSS | 1,634,672 KiB | 1,633,612 KiB median | Effectively unchanged |
| Gain and initial-sum stage | 0.781 s | 0.315 s median | Duplicate full host gain pass removed on resident success |
| TIFF read | 0.734 s | 0.734 s median | Unchanged, host-side cost |

The optimized full-process runs were 3.46, 3.49, and 3.45 s. The 50 ms whole-device samples peaked at 3,537, 3,533, and 3,533 MiB. A separate instrumented one-movie run recorded 2.35 s inside the movie timer; its process wall time is not compared to the unprofiled series. Stage timers are host intervals and may overlap CUDA work. The full-process output gap remains material; its substeps are not yet individually instrumented.

The Nsight trace reports 1,434.8 MB host-to-device, 113.9 MB device-to-host, and 2,735.4 MB device-to-device transfer, essentially unchanged in volume from the baseline. The initial-sum image still returns to the host for existing hot-pixel detection, and the final corrected image returns for output. Do not claim transfers were eliminated. The GPU memory gain is from bounded FFT plans, one shared work area, and a one-frame inverse tile. The time gain is mainly from omitting the second host gain pass.

## Numerical and build gates

- **Current CUDA behavior:** Independent GPU 0 check of the final production binary passed exact MRC pixel equality across all 14,238,980 output pixels, all 24 trajectory shifts, and normalized STAR metadata against PR #51 `08236c2` for the matched `00021 j8/g3` case.
- **Full 24-movie CUDA behavior:** A separate GPU 1 run compared the optimized binary with a fresh build from clean `08236c2`, using the same tutorial `movies.star`, gain, seed, `j4`, and dose/patch options. Both completed all 24 movies. Every corrected MRC pixel and per-frame shift matched exactly, and all normalized per-movie and root STAR fields matched. The baseline build SHA-256 was `6ec086e00e47e9133f0f8367caecb7f5c0bf6873cb758c513bb3609c0c45c54b`. See [the full 24-movie report](issue_50_full24_cuda_exact_comparison.md) and [per-movie JSON](issue_50_full24_cuda_exact_comparison.json). Single-run wall times (64.45 s optimized, 104.90 s baseline) are provenance observations, not a benchmark claim.
- **CPU Gate 2:** Still fails on relative-image RMSE: `0.007130747` versus the `0.001` limit. Shift RMS `0.004159`, shift max `0.006441`, absolute image RMSE `0.005665`, and STAR metadata pass their respective checks. This is an inherited issue; this optimization does not resolve it.
- **Power-spectrum mode:** An independent `j1/g1 --grouping_for_ps 4` run completed twice and produced bit-identical corrected MRC, STAR, and power-spectrum MRC between repeats. It has no pinned CPU power-spectrum parity comparison.
- **Builds:** Final production source compiled with CUDA on the A100 host and with `CUDA=OFF` on the same host. The profiling tool compiled with Python and its Nsight allocation parser reproduced the independent 3,097 MiB high-water; one full CLI movie smoke run completed with input/output hashes and movie timing.

This is a measured improvement, not a release-ready Gate 2 result. Full 24-movie **CUDA-to-CUDA** equality has been checked, while full-dataset CPU/RELION Gate 2, low-memory injection/CPU fallback, no-gain and defect variants, and target-host VRAM headroom remain to be checked. A heuristic specification script reported conformance after the profiling tool was named explicitly in the design, but that script does not override these empirical gates.

## Next optimization decisions

1. Keep the exact current-CUDA parity and CPU/RELION Gate 2 checks as separate acceptance gates. Investigate the relative RMSE failure before declaring numerical parity.
2. Instrument TIFF decode, cuFFT plan construction, upload, hot-pixel statistics, MRC output, and STAR/PDF output separately. The 1.0–1.5 s issue target is not supported by current full-process timings.
3. A GPU hot-pixel statistics/detection design could remove the initial-sum download and host scan, but it must preserve threshold ordering, floating-point behavior, and defect RNG. Compare every corrected pixel and trajectory before accepting it.
4. Explore bounded pinned uploads or overlap of TIFF decoding with transfers only after measuring the extra host memory and failure behavior. Preserve raw frames for a correct CPU fallback.
