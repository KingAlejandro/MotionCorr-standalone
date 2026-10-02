# CUDA Graph / cuFFT contract on the measurement host

Toolkit, library and device actually used — not inferred from a newer release.

| | |
|---|---|
| Device | NVIDIA A100 80GB PCIe, sm_80, persistence mode **Disabled** |
| Driver | 570.86.10 |
| CUDA toolkit | 12.8, `nvcc` V12.8.61 (`/usr/local/cuda`) |
| cuFFT | 11.3.3.41 (`libcufft.so.11.3.3.41`), `CUFFT_VERSION 11303` |
| Host | `4GPUs` / `4-gpu-vm`, payload confined to logical CPUs 96–103 |

## Documented rules that bind this region

**cuFFT** — [cuFFT 12.8 documentation, "CUDA Graphs"](https://docs.nvidia.com/cuda/archive/12.8.0/cufft/index.html):

> "Using CUDA Graphs with cuFFT is supported on single GPU plans."
> "The stream associated with a cuFFT plan must meet the requirements stated in" the
> CUDA Programming Guide's stream-capture section.
> "Every cuFFT plan may be associated with a CUDA stream." … "If no stream is
> associated with a plan, launches take place in `stream(0)`, the default CUDA stream."
> "Each concurrent plan execution needs it's exclusive work area."

The cuFFT page states no restriction on `cufftSetAutoAllocation` / `cufftSetWorkArea`
for capture, and says nothing about plan creation during capture or lazy module
loading. Those gaps were closed by measurement rather than by assumption (below).

**CUDA Programming Guide 12.8**, §3.2.8.7.3 *Creating a Graph Using Stream Capture*:

> "Stream capture can be used on any CUDA stream except `cudaStreamLegacy` (the "NULL
> stream")."

§3.2.8.7.3.2 *Prohibited and Unhandled Operations*:

> "It is invalid to synchronize or query the execution status of a stream which is
> being captured or a captured event…"
> "When any stream in the same context is being captured, and it was not created with
> `cudaStreamNonBlocking`, any attempted use of the legacy stream is invalid… It is
> therefore also invalid to call synchronous APIs in this case. Synchronous APIs, such
> as `cudaMemcpy()`, enqueue work to the legacy stream and synchronize it before
> returning."

§3.2.8.7.3.3 *Invalidation*:

> "When an invalid operation is attempted during stream capture, any associated capture
> graphs are invalidated… `cudaStreamEndCapture()` … will also return an error value and
> a NULL graph."

§3.2.8.7.5.1 *Graph Update Limitations*:

> "Only 1D `cudaMemset` / `cudaMemcpy` nodes can be changed."
> "Changing either the source or destination memory type … or the type of transfer
> (i.e., `cudaMemcpyKind`) is not supported."

§3.2.8.7.5.2 *Whole Graph Update*: the updating graph must be topologically identical
and the dependency specification order must match.

## What this forces on the dose-weighting region

1. **The region cannot stay on the legacy stream.** It needs a dedicated stream, and
   `cufftSetStream` must point the pooled C2R plan at it.
2. **The per-frame telemetry has to go.** The shipped loop performs three
   `cudaEventRecord` / `cudaEventSynchronize` / `cudaEventElapsedTime` triples per
   frame. `cudaEventSynchronize` inside capture is prohibited. A graph arm therefore
   necessarily also removes that telemetry, so a graph-vs-shipped comparison would
   confound two changes; the measurements below always carry a telemetry-free
   stream-ordered arm (`async`) as the control.
3. **The blocking `cudaMemcpy` D2D becomes `cudaMemcpyAsync`.** Required for capture,
   and 1D so the node stays updatable.
4. The copy is 1D, so `cudaGraphExecMemcpyNodeSetParams` can retarget it per frame.

## Measured facts the documentation does not state

Measured with the probe's `--mode faults`, CUDA 12.8 / cuFFT 11.3.3.41 / A100:

| behaviour | observed |
|---|---|
| cuFFT plan creation before capture, first `cufftExecC2R` warmed up outside capture | capture succeeds; 2 cuFFT nodes per C2R |
| Synchronous `cudaMemcpy` while a **non-blocking** stream is capturing | **allowed**, `rc=0`; the copy runs outside the graph and the capture keeps its 5 nodes |
| Synchronous `cudaMemcpy` while a **blocking** stream is capturing | rejected, `cudaErrorStreamCaptureImplicit` (906); graph invalidated, 0 nodes |
| `cufftExecC2R` with the plan left on another stream during capture | **returns `CUFFT_SUCCESS` and captures nothing** — `captured_nodes=0`. The transform executes immediately, outside the graph, with no error anywhere |
| Captured topology | a strict chain: *N* nodes, *N*−1 edges. 24 frames → 217 nodes / 216 edges; 160 frames → 1441 / 1440. Frame accumulation order is preserved and no two accumulation kernels are concurrent |
| Nodes per frame | 1 memcpy + 1 `applyDoseWeightKernel` + 2 cuFFT + 1 accumulation = 5, plus one memset for the movie |

The silent cuFFT escape is the one genuinely dangerous property: a correct-looking
graph that is missing all the transforms. The production arm therefore refuses any
captured graph with fewer than `3 * n_frames` nodes rather than publish a sum from a
partially captured sequence.
