# Issue #226 D3: early streaming admission

The resident-session refusal precedes this check. Before the host reader widens
the movie, the nonresident CUDA path accounts for the full Fourier stack, the
CCF reference/weights/correlation buffers, shifts, and the cuFFT C2R work area.
The work size comes from the actual global-alignment plan with device work
allocation disabled. There is no empirical floor or added safety margin.

Insufficient device memory returns movie failure with a named out-of-memory
message giving required and available bytes. The existing job handler retains
successful movies, withholds joint output and returns nonzero. Fatal CUDA state
is never classified as an ordinary allocation refusal; recoverable pending errors
are cleared. The next movie can still use its own resident route.

`CudaEarlyStreamingOom` declines the first resident session and advertises one
free byte through a test-only memory-query wrapper. It requires early refusal,
no products for the failed movie, no joint STAR and strict products for the next
movie against its standalone control. Production contains no fault switch.

Host-memory exhaustion, genuinely poisoned devices and real smaller GPUs remain
outside this evidence. Admission cannot prevent later allocation failures caused
by another process taking memory or allocator fragmentation.

## Native result

Implementation head: `4cd851677bfda80e60ef189cb1ff668cef721043`, based on
`c8844894c7c6366abf297699b5312e4b775eb5b0`; independent of the D2 branch.
The original QM harness, adapted by `../qm_batch.patch`, ran on the original
GPU1 UUID `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`, CPUs 104–111, under
`/tmp/motioncorr-gpu1-correctness.lock`, checking the bench lock before each run.
CUDA 12.8, driver 570.86.10, nvCOMP 5.3.0.16, GCC 13.3.0, Release.
The four input hashes (10441 movie/gain, Falcon 4 EER and e10216 MRC) were
rechecked against the original QM `input_sha256.txt`: all matched.

Both before and after have 16 runs: four unconstrained references and
G/L × auto/float × 16/21/22 GiB. All eight failed before-controls spend
33.29–42.48 s and reach 36,539–36,541 MiB RSS. All eight after-controls refuse
in 1.13–1.58 s at 743 MiB RSS, name the movie, give required/available bytes,
contain no incompatible-GPU diagnostic, and publish no movie MRC/STAR or joint
STAR. These are single observations on a shared host, not a performance estimate.

At 16 GiB the known buffers alone cannot fit, so the diagnostic gives their
21,414,385,312-byte lower bound. At 21 GiB the plan query includes the work area:
22,673,495,712 required versus 22,096,838,656 available bytes. Both diagnostics
explicitly say "at least"; the first does not allocate a plan just to refine an
already decisive refusal. The measured streaming floor remains 22 GiB.

All four 22 GiB controls complete with products identical to their unconstrained
reference; the four after unconstrained references also match the original
c8844894 references (`cross_baselines.py d3`, all exits 0). Comparison uses the
existing strict-product gate: MRC structure/header/payload, motion STAR and joint
STAR, with only its established writer-timestamp mask. No gate changed.

`native.json` retains commands, inputs, outcomes, diagnostics, RSS, sampled VRAM
(lower bounds), routes, comparisons and cleanup. `grade-before.json` exits 1 on
the unfixed executable's actual results; `grade-after.json` exits 0 (12/12).
Reproduce with `python3 ../grade.py d3 native.json --candidate runs-d3`.

The small `CudaEarlyStreamingOom` native control also passes (1/1): a one-byte
advertised budget after the first session declines, followed by a valid movie
with strict products identical to its standalone reference.

## Re-entry scope

Full CPU CTest on cpu64: 74/74, Release, GCC 13.3.0, CPUs 0–7. The first run
omitted the venv bin directory from PATH and failed `CiFailClosedControls` when
its child tried to execute bare `cmake`; the complete rerun with PATH set passes.
Full CUDA-only CTest: **109/109**; full CUDA+nvCOMP CTest: **112/112** on GPU2
`GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, CPUs 80–87. Both collections pass the
required-test validator; every Release configure/build receipt exits 0.
[Validation metadata](validation.json) and [raw receipts](raw-logs.tgz) include
commands, binary hashes, flags, per-run comparisons, full CTest output and the
CPU64 environment failure followed by its complete passing rerun. The GPU suites
probe the bench lock and hold the GPU2 correctness lock. The input/comparator
metadata read by the harness from `base/` are unchanged from c8844894; the D3
executable is built from the separate frozen `d3-src/` archive.

Not rerun: the complete frozen QF campaign, scientific S1, timing qualification,
macOS, native multi-GPU publication, real smaller GPUs, host-RAM exhaustion,
genuine poisoned-device execution, or optional EER upsampling/binning/PS matrices.
Earlier QF rows retain their original frozen SHA; this is a bounded defect re-entry.

## Current main

The branch incorporates main `36913740` (#247). Its production sources and CMake
configuration are byte-identical to the native-tested implementation head above;
`git diff 4cd85167 -- src CMakeLists.txt` is empty. Main's change is confined to
ProfilingKit tests and documentation. Its compiler-presence control and affected
134-test pass are retained in `docs/post_rc0/issue246/`; current-head CI exercises
that updated test. Native/full-suite receipts here retain their actual tested SHA.
