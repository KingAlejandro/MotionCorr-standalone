# Alignment telemetry waits: exact but no demonstrated useful wall gain

**NO-GO for promotion.** Candidate A+C removes two timing-only waits per alignment
iteration, retaining the movie-owned workspace A and all arithmetic/convergence.
One of three matched pairs was faster; median candidate wall was higher. The
screen does not support expanding this rewrite or adding it to PR130.

Baseline workspace production snapshot: `8bf7c1f151cdb2a1179b1b07a026aceca485a332`
(PR130 latest1420c8c). Candidate production/test snapshot:
`9da3ef9d5ee86058f0a8abf458d9c9d9624eb8e4`; executed head481b0ce adds the compiled
mutant tool only. No global FFT ablation is included. Parent main is frozen
post-PR128 `c499b1d3bf1cceec5c3b194f356844d6f493e7f2`.

## MEASURED complete24-movie process wall, seconds

| Pair / order | Workspace A | A+C | A minus A+C |
|---|---:|---:|---:|
| 1 / A then C | 14.4142693260 | 14.6299135662 | −0.2156442401 |
| 2 / C then A | 13.0524708729 | 14.7608927919 | −1.7084219190 |
| 3 / A then C | 15.0141251639 | 14.8836239430 | +0.1305012209 |

Medians14.414269→14.760893s; ranges13.052471–15.014125 and14.629914–14.883624s;
linear-interpolated IQRs0.980827 and0.126855s. Median paired saving−0.215644s.
The wide baseline variation prevents a precise regression claim, but there is
no repeatable gain. Five confirmation pairs and one-movie timing are **UNRUN**
because the screen was not promising. Candidate-specific stage profiling is
**UNRUN**; calculated2554 fewer waits using a predecessor iteration count is
not a measured wall saving. Do not sum API intervals or infer additive savings.

Dedicated SCARF job3516852, gn0004, A100-SXM4-40GB UUID
`GPU-57be2e4e-89de-a352-97d2-f65f0722338f`; actual payload CPUs0–7, j6/io6,
CUDA12.8, GCC11, nvCOMP5.3, Release/sm80. Same physical device, inputs, options,
filesystem and output regime; no competing compute/build/profile during runs.
Only GPU0 used despite exclusive-node all-four-GPU TRES. Both binaries and
inputs hashed and immutable, with live PID/executable/cpuset/NUMA/device witnesses.
Wall includes launch/output/PDF and observers with up to20ms polling lag.
Do not pool with the earlier workspace campaign or the separate multi-GPU venue.

Median GNU-time maximum-process RSS0.551662→0.551891GiB, CPU use151→150%,
median run-mean sampled GPU utilization43.58→41.37%, sampled device memory
peak3497MiB in all arms. RSS is not simultaneous tree RSS; device sampling is a
lower bound including context/driver reservation. No memory-reduction claim.
All raw observations are in [evidence/campaign-summary.json](evidence/campaign-summary.json).

## Executed gates

- CUDA+nvCOMP41/41, CPU32/32, CUDA-without-nvCOMP40/40.
- All three application pairs passed exact complete non-PDF products:24MRC,
  25STAR,341735520pixels, full normalized1024-byte/extended headers, trajectories,
  metadata/EPS/logs and unique nvCOMP/native-global/600patch/DW witnesses. No
  unexpected warning/fallback; PDFs inventoried without a render-content claim.
- Ten requested-option rows passed exact full structures/products: global1,
  local3/5, selected frames, groups3, no gain, even/odd, save_noDW, power spectrum,
  no dose. Actual runner resident→host retry/reset/convergence control passed.
- Native test checks one/multiple frames, warm reuse, forced nonconvergence,
  input Fourier data and shifts against the predecessor wait ordering. Event
  generation/read gates are deterministic. cuFFT/D2H kept-boundary faults refuse
  later dispatch/success. Immediate cuFFT/D2H/H2D failure drains before cleanup,
  preserves original failure plus a late fatal returned status with cleared
  runtime slot, releases all owned resources and refuses reuse. Invalid device
  and first-allocation guards add no unnecessary drain.
- Actual compiled missing-drain source mutation failed its named assertion for
  all three immediate-failure selectors. Premature k1/k2 elapsed reads failed the
  specific kept-boundary assertion. Each mutation first ran original-binary
  positive controls; unrelated failures cannot count as rejection. All five
  negative controls passed. Independent source/test and separate mutant-tool
  review found no blocker at9da3ef9/481b0ce; reviewers ran no hardware themselves.

The production change defers k1 timing read until the unchanged checked cuFFT
stop, and k2 until unchanged checked D2H stop, before the shared kernel event pair
is re-recorded. Both blocking D2H copies, cuFFT/shift/total waits, launch checks,
kernels, float accumulation and convergence remain. Exception paths drain
submitted work before resource cleanup. No ingest/output/scheduler changes or
new failure framework. [CUDA12.8 event semantics](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-runtime-api/group__CUDART__EVENT.html)
require elapsed reads after completion and before overwriting event generations.

Injected return-status trials are not physical-context poisoning. Genuine
poisoned-context and cross-device cases remain **UNRUN**; historical scientific
truth failures remain distinct. Nothing is merged. Raw campaign and retained
build/test/failure logs: `/work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001`.
See [NEXT.md](NEXT.md) for a source-backed separate follow-up, not another cache
implementation or an assumed dose-normalization gain.

Allocation3516852 completed0:0 and released at2026-10-01T02:25:23+01:00.
Release compute-app inventory was empty; raw evidence remains on SCARF.
