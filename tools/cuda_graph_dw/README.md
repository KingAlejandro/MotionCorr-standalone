# Isolated CUDA Graph harness for the dose-weighted reconstruction

Answers one question: once device buffers and the cuFFT plan are stable, does
CUDA Graph replay cut host submission overhead enough to matter, without
changing the order of device operations?

Nothing here is part of the product build.

## Layout

| file | role |
|---|---|
| `extract_kernels.py` | lifts `FramePolynomial`, `polynomialForFrame` and the three `__global__` kernels verbatim out of `src/acc/cuda/cuda_realspace_dw.cu` into a generated header, and fails the build if a region is missing |
| `graph_dw_probe.cu` | the harness: five submission arms over one device sequence, plus exactness and failure modes |
| `build.sh` | `python3 extract_kernels.py && nvcc -O3 -arch=sm_80 … -lcufft` |
| `run_matrix.sh`, `run_matrix2.sh` | campaign drivers (settle gate, venue record, benchmark/exactness/fault matrices, Nsight counts) |
| `run_app_arms.py` | complete-application arms via `MC_DW_MODE`, with exact product comparison |
| `summarize.py`, `summarize_app.py` | read the JSONL/JSON outputs |

The kernels are extracted rather than copied so the harness cannot drift from the
shipped device code; an exactness result against a hand-copied kernel would only
compare the harness with itself.

## Arms

All five issue the same operations in the same order — memset, then per frame a
D2D copy, `applyDoseWeightKernel`, `cufftExecC2R`, and the accumulation kernel —
and differ only in how that work is submitted.

| arm | submission |
|---|---|
| `prod` | replica of the shipped loop: legacy stream, blocking `cudaMemcpy`, three `cudaEventSynchronize` per frame |
| `async` | one non-blocking stream, async copies, one synchronization at the end |
| `g0` | whole-movie graph captured, instantiated, launched and destroyed inside the timed region |
| `g1` | one-frame graph instantiated once, replayed per frame with node updates |
| `greuse` | whole-movie graph built once, replayed per movie after node updates |
| `greuse_noupdate` | the same graph replayed with no updates — the upper bound on replay, not a usable arm |

## Running

```sh
sh build.sh                               # writes ./build/graph_dw_probe
./build/graph_dw_probe --nx 3710 --ny 3838 --frames 24 --mode bench  --reps 21
./build/graph_dw_probe --nx 3710 --ny 3838 --frames 24 --mode exact
./build/graph_dw_probe --nx 1024 --ny 1024 --frames  4 --mode faults
```

`--mode exact` compares every arm against the `prod` arm byte for byte and runs a
node-update control: the reused graph is built with every frame slot carrying
frame 0's parameters, so a graph that ignored updates would sum frame 0 *n* times
and must fail. At `--frames 1` that graph is already correct, so the control is
reported as inapplicable rather than as a pass.

`--mode faults` ends by faulting the device on purpose and is therefore always
the last thing a process does.
