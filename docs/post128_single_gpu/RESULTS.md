# Workspace-only single-GPU ablation: KEEP for the 24-movie workload

Measured 1 October 2026 against refetched main
`c499b1d3bf1cceec5c3b194f356844d6f493e7f2` (PR128). Main was checked again after
validation and remained unchanged. This is a fresh experiment, not a relabeling
of PR128's 12.93 s or historical PR93 results.

## Complete application wall

One A100-SXM4-40GB, UUID `GPU-57be2e4e-89de-a352-97d2-f65f0722338f`, SCARF
`gn0004`. Payload affinity was verified as logical CPUs **0–7**, `j6/io6`, CUDA
12.8, GCC 11, nvCOMP 5.3, Release/sm80. Both arms used the same tutorial inputs,
filesystems, options and output configuration. The exclusive node had no competing
GPU application. Builds and profiling did not overlap timing.

| MEASURED complete process | Main median (range), s | Workspace median (range), s | Result |
|---|---:|---:|---|
| 24 movies, 3 alternating screening pairs | 13.346 (13.323–13.444) | 12.380 (12.372–12.483) | All 3 candidate runs faster |
| 24 movies, 5 interleaved confirmation pairs | 13.193 (13.122–13.281) | 12.422 (12.367–12.514) | All 5 candidate runs faster |
| One movie, separate 5 interleaved pairs | 2.767 (2.738–2.881) | 2.734 (2.704–2.778) | 4/5 faster; one-movie gain inconclusive |

Confirmation saves **0.771 s / 5.84% by difference of arm medians**. The distinct
median paired saving is **0.717 s**, range **0.676–0.862 s**. IQRs are 0.048 s
(main) and 0.099 s (candidate), using linear-interpolated quartiles. All observations,
paired differences and resource samples are in
[evidence/campaign-summary.json](evidence/campaign-summary.json). Do not treat
these five pairs as a universal speedup or pool them with other venues.

Timing includes launch, `time`/affinity wrappers, output and PDF completion;
monitoring adds up to 20 ms polling lag for 24 movies and 1 ms for one movie.
Raw GNU-time elapsed values are retained as a second observation. GPU observers
were identical between arms; the payload CPU mask was checked while live.
One-movie paired savings span **−0.039 to +0.177 s**, so a robust isolated
one-movie application improvement is **not established** by this sample.

Confirmation median GNU-time maximum RSS is **0.5522 → 0.5525 GiB**; it is a
maximum-process observation, not simultaneous tree RSS. CPU use is **150% → 155%**.
Median run-mean sampled GPU utilization is **46.94% → 47.57%**. Sampled device
memory peak is **3497 MiB** in every 24-movie arm; sampling is a lower bound and
includes context/driver reservation. No VRAM-reduction claim is made.

## Small production delta

`CudaMovieSession` owns a `PatchAlignmentWorkspace`: eight scratch allocations,
eight events, one C2R plan and the exact weight grid. Device, patch/CCF/search
geometry, group count, B-factor and downsample participate in the key.
Initialization publishes no stale key on failure. Replacement invalidates first
and uses the existing fixed scoped owners and `CudaFailureState`.

The local resident path borrows that workspace. Checked release occurs before
reconstruction/publication. The original entry point/signature remains for global
alignment and host fallback; it retains ephemeral cleanup and emits completion
only after successful cleanup. Fatal state refuses reuse/redispatch.

Kernels, host shift accumulation, convergence, FFT/scaling arithmetic, RNG and
all synchronization calls are unchanged. No PR93 wholesale import, static cache,
fast math, prefetch, ingest/output redesign or multi-GPU modification is included.

## Fresh profile: MEASURED, inclusive and overlapping

| Instrumented observation | Main | Workspace |
|---|---:|---:|
| Local alignment, 600 calls | 1.893 s | 0.930 s |
| cuFFT MakePlanMany calls | 720 | 144 |
| MakePlanMany inclusive CPU intervals | 1.471 s | 0.541 s |
| cudaMalloc / cudaFree calls, each | 5544 | 936 |
| Event create / destroy calls, each | 5184 | 576 |
| cudaDeviceSynchronize calls | 1248 | 1248 |
| cudaEventSynchronize calls | 8761 | 8761 |
| GPU kernel busy interval union | 3.404 s | 3.400 s |
| Traced device allocation peak | 3196668336 B | 3196668336 B |
| Traced pinned reservation | 167772160 B | 167772160 B |

These profile intervals are **not additive wall components** and exclude untraced
context/driver allocations. The fresh baseline also measured session initialization
0.405 s, compressed read/repack 1.223 s, nvCOMP ingest 2.965 s, final D2H 0.125 s,
MRC statistics 0.334 s, payload writing 1.136 s and close 1.711 s, with overlap.
No residual interval is assigned to an unmeasured stage.

The initial profile had a setup/release labeling bug and incomplete cuFFT wrapper
coverage (696 plans). It is retained as `profile-summary.json`; corrected
`profile2-summary.json` is the baseline used above. Instrumented candidate output
also passed the complete non-PDF tree gate. Profiler wall is not the performance
claim.

## Acceptance evidence

Native uninstrumented source snapshot: `8bf7c1f151cdb2a1179b1b07a026aceca485a332`,
tree `9b6042c90072932e3ca9f7cd304b228e28461476`. Later commits add tools/evidence;
`src/`, CMake and tests remain identical to that tested snapshot.

- **Exact application:** all 3 screening + 5 confirmation pairs passed complete
  non-PDF inventory/content comparison: 24 MRCs, 25 STARs and **341735520 pixels**
  per arm, full normalized 1024-byte/extended headers, trajectories, metadata and
  EPS/log products. Each arm had unique movie-associated nvCOMP witnesses and
  native global/600 patch/DW witnesses, with no unexpected fallback.
- **Requested options:** global 1×1, local 3×3/5×5, selected frames, groups of 3,
  no gain, even/odd, save_noDW, power spectrum and no dose weighting all passed
  independently checked inventories, full MRC structures/pixels and exact
  non-PDF trees. One-movie timing pairs passed the same exact gate.
- **Native workspace matrix:** 13 exact actual-path input/key/movie controls,
  three zero-setup reuse calls, 18 initialization failures/recoveries, populated
  A→B partial/fatal replacement, checked cleanup, completion-marker withholding
  and fatal reuse refusal passed.
- **Discriminating controls:** native always-rebuild and missing-B-key mutants
  failed the resource/key assertion. Real-runner recoverable/fatal cleanup
  injection refused products and released owned allocations. A mutant removing
  only the checked-release guard published success under the recoverable fault
  and was rejected. Actual resident-to-host retry reset shifts and converged.
- **Build/test compatibility:** CPU **32/32**, CUDA without nvCOMP **39/39**,
  CUDA+nvCOMP **40/40**, including existing preprocessing/reconstruction failure
  controls. No tolerance, gate or required test was relaxed.
- **Independent source review:** narrow completion-order/replacement-test findings
  were fixed before native validation; the reviewer approved the repaired source.

Retained failures: the first build failed a test-only `const RelionError` stream
usage; fixed in `8bf7c1f`. The archive initially failed an unchanged Git-backed CI
control because its error text differed without Git metadata. Restoring the pinned
repository metadata yielded 40/40 with unchanged assertions. Both failed logs
remain under `evidence/`.

Limits: one venue/toolchain/workload; one-movie speedup inconclusive; physical
cross-device cache switching and genuinely poisoned hardware are **UNRUN**.
Fault controls substitute returned codes after actual calls; they do not poison
hardware. PDFs are inventoried, not content/render compared; exact EPS data and
other non-PDF products do not erase that scope limitation. This is same-backend
regression evidence, not a new truth/upstream scientific acceptance study.

## Provenance and next action

Raw outputs, input/binary/source hashes, payload identities, masks/NUMA maps,
GPU samples, Nsight reports/SQLite and commands are retained at
`/work4/scd/scarf1415/motioncorr/post128-sgpu-20261001`. Smaller evidence is in this
folder, including the paired manifest/structure reports. Baseline and candidate
binary hashes are in `evidence/final-artifacts.sha256`.

SCARF allocations 3516825/3516842 preserve the failed build/archive test attempts;
3516844 completed the accepted campaign and released at
`2026-10-01T01:15:36+01:00`, with an empty compute-app list. The unrelated VM and
multi-GPU branch/harness were untouched.

**Disposition:** retain this bounded workspace candidate for review, based on
repeatable complete 24-movie application benefit. No merge is authorized here.
Next ablation is global FFT synchronization alone, after checking installed cuFFT
ordering/workspace requirements and designing asynchronous-error visibility
controls. Keep it separate from this workspace commit and do not infer additivity.
