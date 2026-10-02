# CUDA Graph replay for the dose-weighted reconstruction — NO-GO

**Question.** Once resources are stable, can CUDA Graph replay reduce host
submission overhead enough to matter without changing operation order?

**Answer.** Operation order is preservable and output is bit-exact, but there is
nothing to recover. The whole host submission cost of the region is **1.2 ms per
movie**, of which replay removes about **1.0 ms of host CPU and 0 ms of wall**,
because the region is device-bound. Building the graph per movie costs
**1.12 ms**, so the per-movie graph arm is a measured **+0.94 ms/movie
regression** against its own control (157/168 paired movies slower). Replay does
pay where per-operation device work is small — −9.9% at 256×256 × 160 frames,
20/20 reps — and MotionCorr's geometry is two orders of magnitude away from that.

This result is independent of the earlier alignment-synchronization no-go and does
not rest on it. It does, however, reproduce a *different* finding on its own
evidence: removing the per-frame event telemetry is worth **−2.31 ms/movie**
(161/168 paired movies faster), four times more than graphs could ever return.

## SOURCE

| | |
|---|---|
| Branch | `exp/dw-cuda-graph`, experimental, **not merged** |
| Parent | `bed17cd` on `t3code/cf0d9d86` |
| Candidate | `4a68ecf` (`src/acc/cuda/cuda_realspace_dw.cu` + `tools/cuda_graph_dw/`) |
| Extracted kernel text | sha256 `0306a5d566214da4e3a291c8c7ac869017f1ba022a98606cd53b859163687d55` |
| Venue | `4GPUs` / `4-gpu-vm`, A100 80GB PCIe `GPU-eddb42fe-…`, CPUs 96–103, CUDA 12.8, cuFFT 11.3.3.41, driver 570.86.10 |
| Inputs | RELION 3.0 tutorial, 24 movies, `movies.star` sha256 `fb998f70…0041` (matches the repo manifest) |

`MC_DW_MODE` selects the arm; unset is the shipped path and is byte-for-byte the
original loop. Nothing is enabled by default.

## CUDA/CUFFT CONTRACT

Full quotations, versions and the measured gaps are in
[CUDA_CONTRACT.md](CUDA_CONTRACT.md). The four consequences for this region:

1. The region must leave the legacy stream; `cufftSetStream` must follow.
2. `cudaEventSynchronize` is prohibited inside capture, so the graph arm
   necessarily also deletes the per-frame telemetry. **Every comparison below
   therefore carries a telemetry-free stream-ordered `async` arm as the control**;
   graph-vs-shipped on its own would confound two changes.
3. The blocking D2D `cudaMemcpy` becomes `cudaMemcpyAsync`; it stays 1D, so the
   node remains updatable.
4. Measured, not documented: **a cuFFT plan left on another stream during capture
   returns `CUFFT_SUCCESS`, executes immediately outside the graph, and yields a
   valid graph with zero nodes.** Silent. The candidate refuses any captured graph
   with fewer than `3 · n_frames` nodes for this reason.

## GRAPH_REGION

Per movie: one memset, then per frame a D2D copy of the Fourier frame,
`applyDoseWeightKernel`, `cufftExecC2R`, and the accumulation kernel
(`interpolateAndAccumulatePolynomialKernel`, or `accumulateDirectKernel` for the
null model). The D2H of the sum stays outside the graph, at the publication
boundary.

Captured topology is a **strict chain** — *N* nodes, *N*−1 edges — at every frame
count measured: 24 frames → 241 nodes / 240 edges, 80 → 801/800, 160 → 1601/1600.
Five nodes per frame (1 memcpy + 1 dose-weight + 2 cuFFT + 1 accumulate) plus the
memset. Frame accumulation order is preserved and no two accumulation kernels are
ever concurrent. No parallel reduction is introduced.

### What varies, and where

| quantity | scope | how a reused graph absorbs it |
|---|---|---|
| frame offset into `d_Fframes` | per frame | memcpy node source (1D, updatable) |
| `iframe` | per frame | dose-weight kernel parameter |
| `coeff.x[0..5]`, `coeff.y[0..5]` | per frame | accumulation kernel parameters (derived from the model and `iframe`) |
| `d_doses` **contents** | per movie | device buffer, **not** a node parameter — rewritten by H2D, no graph update needed |
| `d_Fframe`, `d_Iframe`, `d_Isum` | per movie today | every kernel and the memcpy destination; these are `cudaMalloc`ed per call, so they move every movie |
| `apix`, `n_frames` | per movie | kernel parameters; a different `n_frames` also changes node count → **re-capture, not update** |
| `nx`, `ny`, grids, `sz_fframe` | per geometry | kernel parameters and memcpy extent; a different geometry also needs a different cuFFT plan → **re-capture** |

So at fixed geometry and frame count a movie needs **3 node updates per frame**
(72 at 24 frames) plus nothing else. A frame-count or geometry change forces
re-instantiation.

## GRAPH_BUILD_COST — experiment G0

Measured **inside the complete application**, from the candidate's own log line,
168 movies:

| | median | range |
|---|---:|---|
| capture | 0.385 ms | 0.280–1.330 |
| instantiate | 0.600 ms | 0.440–1.720 |
| destroy | 0.160 ms | 0.120–3.500 |
| **total per movie** | **1.120 ms** | 0.860–6.130 |

Native harness, same quantity, by frame count at 3710×3838 (capture + instantiate):

| frames | nodes | capture | instantiate | ≈ per node |
|---:|---:|---:|---:|---:|
| 24 | 241 | 0.505 ms | 1.097 ms | 6.6 µs |
| 80 | 801 | 1.640 ms | 4.909 ms | 8.2 µs |
| 160 | 1601 | 4.947 ms | 12.052 ms | 10.6 µs |

Construction scales slightly worse than linearly in node count, so **G0 gets worse
with longer movies, not better** — the opposite of the direction that would make
per-movie graphs viable for the 160-frame workload.

G0 loses at every frame count tested. Paired against the `async` control in the
native harness, the `g0` arm is +2.86 ms (24 frames), +4.92 ms (80), +6.88 ms (160)
at 3710×3838 — each matching that geometry's build cost. **Graph construction is
not hidden anywhere in these numbers; it is inside the candidate's timed region.**

## REPLAY_COST — experiment G1

Native harness, graph built once outside the timed region and replayed per movie
with stable buffers and a stable plan (`greuse`), against the `async` control.
Medians over paired reps, cold first rep dropped.

| geometry × frames | host submit CPU, async → greuse | region wall, greuse − async | reps faster |
|---|---|---:|---|
| 3710×3838 × 24 | 1.245 → 0.278 ms | +0.465 ms | 8/20 |
| 3710×3838 × 80 | 3.451 → 0.557 ms | −0.652 ms | 8/14 |
| 3710×3838 × 160 | 204.98 → 0.832 ms | −1.204 ms | 7/10 |
| 3838×5760 × 24 | 1.157 → 0.283 ms | +0.361 ms | 8/20 |
| 512×512 × 160 | 3.828 → 0.971 ms | +0.200 ms | 1/20 |
| **256×256 × 160** | 2.744 → 0.352 ms | **−0.325 ms (−4.9%)** | **19/20** |
| 256×256 × 160, no updates | 2.744 → 0.029 ms | **−0.652 ms (−9.9%)** | **20/20** |
| 512×512 × 160, no updates | 3.828 → 0.050 ms | **−0.726 ms (−5.3%)** | **20/20** |

Reading of this table:

- **Host submission CPU is genuinely removed** — 1.2 ms → 0.3 ms at tutorial
  geometry — and **does not appear in the wall**, because the host is never the
  thing the region is waiting for.
- **Node updates cost about half the available saving.** 72 updates at 24 frames
  take 0.178 ms (2.5 µs each); 480 at 160 frames take 0.713 ms (1.5 µs each). The
  `no updates` rows are an upper bound on replay, not a usable arm: a real movie
  changes the frame offsets and the polynomial coefficients.
- **Replay only pays when per-operation device work is small.** The effect is
  clean and repeatable at 256×256 (20/20) and vanishes by 3710×3838.
- At 160 frames the `async` submit-CPU figure (205 ms) is **launch-queue
  back-pressure**, not submission work: the device falls far enough behind that the
  host blocks inside the launch call. A graph avoids that blocking entirely and the
  wall still does not move, which is the same conclusion stated a second way.

A one-frame graph replayed per frame (`g1`) is not useful: each `cudaGraphLaunch`
costs ~17 µs, more than the per-operation launches it replaces. Whatever benefit
exists comes from one launch for the whole movie.

## MEASURED — complete application

24 tutorial movies, canonical options (`--use_own --dose_weighting
--dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref
Movies/gain.mrc --seed 1 --gpu 0 --j 6 --max_io_threads 6 --ingest nvcomp`),
one binary, 7 rounds, arm order rotated each round.

**Reconstruction region, per movie** (the product's own event pair; 168 paired
(round, movie) cells per comparison):

| arm | median ms | paired delta | movies faster |
|---|---:|---|---|
| product (shipped) | 46.01 | — | — |
| async control | 43.61 | **−2.31 ms vs product** | 161/168 (96%) |
| graph | 44.67 | −1.38 ms vs product | 157/168 (93%) |
| graph | | **+0.935 ms vs async** | **21/168 (12%)** |

The +0.935 ms penalty and the 1.120 ms measured build cost agree. The graph arm
buys back at most ~0.19 ms of the construction it pays for.

**Complete process wall, 24 movies, 7 paired rounds:** product 9.974 s, async
9.582 s, graph 9.492 s. Paired graph − async: median −0.045 s, range −1.083 to
+1.674, 4/7 faster. **Nothing is established at process level** — n=7 against that
spread cannot resolve a 50 ms effect, and the region evidence above says the true
sign is the other way.

**80- and 160-frame application workloads are UNRUN**; no tutorial movie has more
than 24 frames and no longer movie was staged. Those frame counts are covered in
the native harness only, where the graph arm is no better and G0 is worse.

**Nsight counts** (`--trace=cuda`, 3 reps, 3710×3838 × 24): the product arm issues
432 `cudaEventRecord` and 216 `cudaEventSynchronize` costing 76 ms of host time;
the reuse arm issues 144 `cudaGraphExecKernelNodeSetParams` and 72
`cudaGraphExecMemcpyNodeSetParams` costing ~3 ms, and ~500 fewer `cuLaunchKernel`.
These per-arm totals include fixed per-process setup that every arm pays, so only
the structure is meaningful, not the absolute differences; the probe's own
`CLOCK_THREAD_CPUTIME_ID` figures above are the controlled measurement.

**Not a clock artifact.** Persistence mode is off on this host, so SM clock was
sampled at 250 ms throughout: median 1395 MHz of a 1410 MHz maximum, 97.1% of
samples ≥1300 MHz.

## EXACTNESS

Bit-exact, by `memcmp` of the full reconstructed image against the product arm —
no RMSE substitution anywhere.

Native harness, **42 configurations** across two campaigns, all five arms
(`prod`, `async`, `g0`, `g1`, `greuse`) identical in every one:

- frames 1, 2, 8, 24, 80, 160 × {polynomial model, null model} at 3710×3838 and
  3838×5760;
- non-square 1024×768 and 768×1024; odd `ny` 512×511 and 510×513;
- doses zero, ramp and high; `apix` 0.5, 0.885 and 2.0.

**Node-update control.** A reused graph that silently ignored updates would still
produce the right answer if it were built with the right parameters, so the
control builds it with the *wrong* ones: every frame slot carries frame 0's
parameters. Replaying without updates must differ from the reference, and
replaying after updates must match it. Both held in all 38 applicable
configurations. At `frames=1` that graph is already correct, so the control cannot
observe anything and is reported **inapplicable**, not as a pass — 4 configurations.

Complete application: all 24 MRCs, STARs, trajectories, metadata, EPS and logs
compared between the product and candidate arms with
`docs/issue85_laneC/compare_output_trees.py`. **This comparison is currently
re-running**: the first pass invoked bare `python3`, which has no numpy on this
host, so all 14 comparisons errored before reading a byte. No PASS is claimed from
it yet. The arms' per-movie reconstruction numbers above come from the run logs
and are unaffected.

A positive witness confirms the path ran: all 24 logs in every async round carry
`DW submission mode: async`, all 24 in every graph round carry
`DW submission mode: graph`, no product log carries either, and no arm's logs
carry another arm's marker.

## FAILURE_CONTROLS

`--mode faults`, CUDA 12.8 / A100. Nine cases; `publish_allowed=no` means the
failure was detected before any sum could be returned.

| case | detected at | code | publishable |
|---|---|---|---|
| `cudaEventSynchronize` inside capture | `cudaEventSynchronize` | 901 | no — null graph returned |
| sync `cudaMemcpy`, capture on a **non-blocking** stream | — | 0 | **allowed by contract**; copy runs outside the graph, 5 nodes still captured |
| sync `cudaMemcpy`, capture on a **blocking** stream | `cudaMemcpy` | 906 `StreamCaptureImplicit` | no — graph invalidated, 0 nodes |
| `cufftExecC2R` with the plan on a foreign stream | **nothing** | `CUFFT_SUCCESS` | **silent escape** — 0 nodes captured, transform ran immediately |
| zero-grid kernel during capture | `cudaGetLastError` | 9 | no |
| instantiate with an invalid flag word (injected) | `cudaGraphInstantiateWithFlags` | 1 | no |
| launch into a capturing stream | `cudaGraphLaunch` | 900 | no |
| memcpy node update with an invalid pointer | `cudaGraphExecMemcpyNodeSetParams` | 1 | no — refused before launch |
| device fault inside a replayed graph | `cudaStreamSynchronize` | 700 `IllegalAddress` | no |

Two notes on the cases that did **not** produce an error:

- The non-blocking-stream `cudaMemcpy` row is the documented behaviour, and it is
  good news for integration: the product's other synchronous copies elsewhere are
  not made illegal by a capture in progress on a dedicated non-blocking stream.
- The cuFFT escape is the one real hazard. It cannot be caught by an error code,
  only by counting nodes, which is what the candidate does.

**No error is made newly fatal.** The capture-escape refusal records
`cudaErrorStreamCaptureInvalidated`, which `cudaErrorPoisonsContext()` does not
classify as poisoning, so the CPU dose-weighting fallback remains available exactly
as on the product path. The one case that does poison the context —
`cudaErrorIllegalAddress` from a device fault — poisons it identically whether the
kernel ran inside a graph or not.

**Error attribution is genuinely weaker inside a graph**, and that is not fixable.
On the stream path `cudaGetLastError()` after each launch names the failing
operation; a graph launch reports one error for the whole replay, so a device fault
in frame 97 is indistinguishable from one in frame 3. That is a real cost of this
design, independent of performance.

A drain-before-destroy defect found in the candidate during review is fixed in
`4a68ecf`: a submission that failed part way through left work queued on the
stream while the scoped owners freed the buffers it reads. `ScopedCudaStream` now
synchronizes before destroying.

## LIMITATIONS

- **One venue, one device.** A100 80GB PCIe, CUDA 12.8, cuFFT 11.3.3.41. Nothing
  here transfers to another toolkit or architecture without re-measurement; graph
  launch and instantiate costs are driver-version properties.
- **The box was shared.** Load average was 11–14 during campaign 2 from two other
  sessions, which is why several native paired ranges span ±100 ms around a
  sub-millisecond median. The medians are over 10–20 paired reps with arms
  interleaved, and the small-geometry rows (20/20 one way) are unaffected by it,
  but no native figure here is a clean-room number. The application region
  comparison (n=168 paired) is the robust one.
- **Process-level application wall is n=7.** It establishes nothing and is reported
  as such.
- **80- and 160-frame application runs are UNRUN** — harness only.
- **`g0` is the only shape the application arm implements.** Reusing an executable
  graph across movies requires caching it on the worker, which this task excludes;
  the reuse case is measured in the harness only, with the buffer and plan
  stability that a reusable worker would have to provide.
- `CiFailClosedControls` fails in this build. It is the known `git archive`
  artifact — the staged tree has no `.git`, so a control asserting on a git-ref
  error message gets the archive-mode message instead. 41/42 other tests pass,
  including all 10 CUDA tests. Not caused by this change.
- The harness's first wall measurement included an 88 MB host-side digest inside
  the timed region, inflating absolute region walls roughly fourfold. Paired
  deltas and submission-CPU figures were unaffected. The fix is in the probe and a
  re-measurement of the absolute walls is queued; the tables above quote deltas,
  and absolute region size comes from the application's own measurement (46 ms).

## INTEGRATION_REQUIREMENTS

If this were ever revisited, these are the preconditions — recorded because they
are what the experiment actually established, not as a recommendation to proceed.

1. **A reusable worker that keeps `d_Fframe`, `d_Iframe`, `d_Isum` and the cuFFT
   plan at stable addresses across movies.** Today they are `cudaMalloc`ed per
   call. Without this, only G0 is possible, and G0 is a measured loss.
2. **Invalidation keyed on device, `nx`, `ny`, `n_frames` and the plan handle.** A
   frame-count or geometry change alters node count and requires re-instantiation,
   not update.
3. **A node-count assertion after every capture.** The cuFFT escape is silent and
   produces a plausible, wrong result.
4. **Capture mode must be `cudaStreamCaptureModeThreadLocal` or stricter
   reasoning about the OpenMP threads.** The default `Global` mode constrains
   unrelated API calls in other threads for the duration of the capture, and
   MotionCorr runs 6–8 OpenMP workers.
5. **Accept weaker error attribution**, or keep a non-graph path for diagnosis.
6. **Keep the `async` arm separate.** It is where the measured benefit is.

## NEXT

1. **Do not pursue graphs for this region.** The ceiling is 1.2 ms of host CPU per
   movie that does not convert to wall, against a 1.12 ms construction cost.
2. **The telemetry removal is worth a separate, properly scoped change**: −2.31 ms
   per movie, 161/168 paired movies faster, bit-exact, and it needs no graph, no
   stream capture and no worker-lifetime change. It does delete the per-stage
   `Dose Weighting Kernel` / `cuFFT C2R Execution` / `Interpolation & Accum` log
   lines, which is a product-visible change and needs its own sign-off. That is a
   proposal, not a merge.
3. If a long-frame EER workload (≫160 frames at small binned geometry) ever becomes
   a target, the 256×256 row is the only place replay helped, and the question
   would be worth re-asking **for that geometry specifically**.
