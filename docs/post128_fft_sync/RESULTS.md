# Global FFT synchronization ablations: no demonstrated useful gain

Main `c499b1d3bf1cceec5c3b194f356844d6f493e7f2` (merged PR128).
FFT-only tested source: `84ba8b38e95640d56906de972e1dbaf791149fb3`.
Workspace + FFT tested source: `1c380f4930b421604961ef5a816b79656f56480a`.
Workspace comparator: PR130 production snapshot `8bf7c1f151cdb2a1179b1b07a026aceca485a332`.

## Disposition

**NO-GO for promotion as a performance change.** Exactness and failure controls
passed, but FFT-only confirmation was slower by median and only 2/5 pairs were
faster. Adding the change to the workspace also failed to show a repeatable
application benefit (1/3 paired wins). Do not add this code to PR130 or infer
additive savings. Retain separate experimental branches and evidence.

## MEASURED complete application wall, seconds

| Comparison | Baseline observations | Candidate observations | Median baseline → candidate |
|---|---|---|---|
| Main / FFT screen | 13.516513, 13.534892, 13.835840 | 13.429851, 13.419141, 13.350520 | 13.534892 → 13.419141 |
| Main / FFT confirmation | 13.765339, 13.416361, 13.688090, 14.829268, 12.923519 | 13.467004, 13.877513, 13.828280, 14.467584, 12.940496 | 13.688090 → 13.828280 |
| Workspace / workspace+FFT screen | 14.323398, 14.524449, 14.640636 | 14.441262, 14.555250, 14.411133 | 14.524449 → 14.441262 |

Baseline-minus-candidate paired differences:

- FFT screen: +0.086662, +0.115751, +0.485319.
- FFT confirmation: +0.298335, −0.461152, −0.140190, +0.361685, −0.016976.
- Workspace+FFT screen: −0.117863, −0.030801, +0.229503.

Ranges/IQRs, using linear-interpolated quartiles:

| Series | Baseline range / IQR, s | Candidate range / IQR, s |
|---|---|---|
| FFT screen | 13.516513–13.835840 /0.159663 | 13.350520–13.429851 /0.039665 |
| FFT confirmation | 12.923519–14.829268 /0.348978 | 12.940496–14.467584 /0.410509 |
| Workspace+FFT screen | 14.323398–14.640636 /0.158619 | 14.411133–14.555250 /0.072058 |

[Campaign summary](evidence/campaign-summary.json) contains every CPU-use,
maximum-process RSS, sampled GPU-utilization and device-memory observation;
these are not process-tree RSS or allocator-only VRAM figures.

Three alternating screens followed by five interleaved FFT confirmations.
The combination was independently screened; five combination confirmations
remain **UNRUN** because its screen was not promising. One-movie FFT timing
and an FFT-specific profiler comparison are **UNRUN**. No stage savings or
causal allocation/NUMA claim is inferred from these whole-process timings.

Dedicated SCARF job3516852, gn0004, A100-SXM4-40GB UUID
`GPU-57be2e4e-89de-a352-97d2-f65f0722338f`, actual payload logical CPUs0–7,
j6/io6, CUDA12.8/GCC11/nvCOMP5.3, Release/sm80. Only GPU0 used even though
exclusive-node TRES covers all four GPUs. Identical inputs, output options,
filesystem and observers; no competing compute, build or profile during timing.
Do not pool with the earlier PR130 campaign or other venue/resource series.
Wall includes launch, output/PDF completion and observers (up to20ms polling lag).
Complete unrounded observations, GNU-time maximum-process RSS/CPU observations,
source/binary/input hashes and live payload/device witnesses are retained remotely.
The compact raw records and exact verdicts are under [evidence](evidence).

## Correctness and failure contract

FFT-only: CPU32/32, CUDA-without-nvCOMP39/39, CUDA+nvCOMP40/40.
Workspace+FFT: CUDA+nvCOMP41/41. All executed application timing pairs and both
ten-row option matrices passed exact complete non-PDF tree comparison: full
normalized1024-byte/extended MRC headers, all341735520 pixels, 24MRC/25STAR,
trajectories, metadata and unique native nvCOMP/global/600patch/DW witnesses.
Option matrices include global1, local3/5, selected frames, groups3, no gain,
even/odd, save_noDW, power spectrum and no dose. Actual resident→host retry/reset
caller controls passed. PDF presence/inventory only, no PDF-content claim.

The new native FFT test compares previous per-frame synchronization with the
candidate for three multi-frame geometries, exact spectra/inverse/preserved
Fourier data. It checks forward/inverse completion boundaries, failed init and
immediate frame2 R2C/C2R/D2D failure followed by drain-only fatal status with
cleared pending error. Original failure cause remains, fatal reuse is refused
and resources are released. Five actual compiled production mutants (missing
forward/inverse boundary, forward drain, inverse-exec drain, inverse-copy drain)
were rejected by their named assertions after positive controls passed.
These are injected returned errors, not physically poisoned CUDA contexts.

Production only queues unchanged same-plan, default-stream transforms and
moves completion to checked consumption boundaries. Inverse tile copy/transform
order and forward scaling remain unchanged. An immediate failure drains earlier
submitted work before fallback/cleanup and retains late fatal status. No kernels,
float arithmetic, ingress, output or scheduler changes. Bounded independent
source review found no remaining blocker at84ba8b3; this does not turn the
performance result into a win.

[NVIDIA cuFFT12.8 streamed transforms](https://docs.nvidia.com/cuda/archive/12.8.0/cufft/index.html#streamed-cufft-transforms)
and [CUDA12.8 synchronization behavior](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-runtime-api/api-sync-behavior.html)
support this narrow same-stream ordering. They do not justify concurrent execution
on the same workspace or a cross-stream redesign.

Raw campaign: `/work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001`.
Retain all failures, superseded observations and unrun rows. Historical scientific
truth failures and physical-context/cross-device acceptance gaps remain separate.
No merge is authorized or performed.

Allocation3516852 completed0:0 and released at2026-10-01T02:25:23+01:00;
release compute-app inventory was empty. Evidence remains retained remotely.
