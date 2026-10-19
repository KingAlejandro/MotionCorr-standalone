# Genuine CUDA sticky-context control (#213)

Test-only change based on main `c8844894`. Production sources, existing injected
tests, numerical gates and tolerances are unchanged. Native results are recorded
below only after execution; the frozen RC0 qualification remains on `6d68e2d6`.

## Design and acceptance

`motioncorr_sticky_fault` links the real runner/core, the existing retry-caller
shim, and a new `.cu` shim. The caller shim forces one completed, nonconverged
patch so that the real `downloadPatchSpectra` runs. At its first `cudaMalloc`, the
new shim launches a one-thread null-pointer device write in the same process and
CUDA context. It synchronizes, clears the host last-error slot, then executes the
original product allocation. Neither that allocation's return value nor any
other CUDA status is fabricated. Required witnesses are native error 700 from
both the fault completion and the subsequent product `cudaMalloc`.

The driver requires the runner's refusal naming the faulting movie and patch,
exit **1**, no products or partial files (diagnostic logs are allowed), and no
further product kernel dispatch. It covers a single movie and three movies in
one process; all three must be attributed as failed and the two later movies
must not dispatch kernels or publish products. A fresh healthy process must
first complete the real resident retry and publish its image and completion
STAR. The single-worker `run_dataset.py` arm requires a failed worker, dataset
FAIL, completed process cleanup, and no aggregation. This is an endpoint failure
control on one GPU, not multi-device success/scaling qualification.

The test is absent by default. Enable **`MC_ENABLE_STICKY_CUDA_TEST=ON`** explicitly
in a Release CUDA build; its labels are `cuda;hardware;destructive;opt-in`.
The driver requires Linux, at most eight allowed CPUs, and a full GPU UUID. It
acquires `/tmp/motioncorr-gpuN-correctness.lock` itself, probes the benchmark lock,
and requires an idle GPU (no compute processes, zero utilization, at most 128 MiB
used) before faulting. Do **not** wrap the driver in the same GPU flock.
It records `nvidia-smi -q`, identity/occupancy/ECC queries before and in `finally`
afterward, requires unchanged uncorrected volatile ECC and no reported recovery
action, and never resets a device. An unhealthy post-run device makes the test
fail. Fresh process contexts isolate the arms. Child deadlines and the CTest
deadline fail rather than accepting a timeout as the expected fatal status.

## Reproduction on 4GPUs

Use an idle GPU UUID and a free eight-CPU allocation after checking occupancy.
Scratch must be under `/mnt/clathrin/alex-motioncorr-213`. Transfer a committed
snapshot with `git archive` (not macOS tar). For example, from that source tree:

```sh
taskset -c 80-87 cmake -S src -B build-cuda -DCMAKE_BUILD_TYPE=Release \
  -DCUDA=ON -DUSE_NVCOMP=OFF -DBUILD_TESTING=ON \
  -DMC_ENABLE_STICKY_CUDA_TEST=ON \
  -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3
taskset -c 80-87 cmake --build build-cuda --target motioncorr_sticky_fault -j8
CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 \
  taskset -c 80-87 /home/alex/.mc-venv/bin/python3 src/tests/run_sticky_cuda_control.py \
  --binary build-cuda/motioncorr_sticky_fault --workdir control-cuda
```

Check configure/build exit statuses. Repeat on a CUDA+nvCOMP build with its
actual nvCOMP installation recorded. `ctest -R '^CudaStickyContext$' -V` is the
registered equivalent; use the direct command to retain a named evidence tree.
The driver records binary/input hashes, commands, exit statuses, console logs
and GPU health snapshots. Retain toolchain/build logs and the source SHA too.

## Detection mutant (uncommitted)

In a separate scratch copy of the same source, change only the fatal decision
immediately following the runner's `downloadPatchSpectra` call:

```cpp
if (decision.verdict == CUDA_RETRY_FATAL) {
```

to `if (false && decision.verdict == CUDA_RETRY_FATAL) {`. Leave every other
fatal check intact. Build the same test executable in Release and run the
unchanged driver. The mutant must still witness the genuine 700/700 pair and
then fail the driver's attributed-refusal assertion. It may subsequently fail
on another real CUDA call; that failure alone does not count as correct
containment at this boundary. Do not commit the mutant or call a synthetic
transcript check a compiled-mutant result.

## Evidence

Local checks on the implementation (`faba8961`, final driver `f25c9580`):

- `python3 -m py_compile tests/run_sticky_cuda_control.py`: exit 0.
- Release CPU CMake configure: exit 0 with a task-specific Python/numpy venv;
  `ctest --show-only=json-v1`: 74 collected, `CudaStickyContext` absent. No CPU
  executable was built or CTest run. The first configure, using Homebrew Python
  without numpy, failed as required; the explicit venv corrected it.
- A synthetic-transcript predicate probe accepted a complete expected record
  and rejected missing launch/fault/sticky-call/refusal witnesses, wrong movie,
  post-fault kernel, exit 0/signal/timeout, and a `.mrc.part` file. This checks
  grading only; it executes no CUDA and is not the compiled runner mutant.

Native source/test head: **`f25c958041cc59e6b6c9d2336c7f85092b0fff81`**.
The 451 archived build-source/test/tool files on the host match this commit's
local SHA-256 manifest exactly after restoring the mutant. Subsequent changes
only publish documentation/evidence. Raw records are in [`evidence/`](evidence/):

- `4-gpu-vm`, A100 80 GB PCIe GPU2
  `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, driver 570.86.10, CUDA 12.8.61,
  GCC 13.3.0, nvCOMP 5.3.0.16 in the nvCOMP build. All builds/runs used CPUs
  80–87; movie runs used `--j 4 --max_io_threads 2`. No timing was measured for
  comparison. Scratch: `/mnt/clathrin/alex-motioncorr-213`.
- Release **CUDA and CUDA+nvCOMP** configure/build: exit 0. The unchanged driver
  on each configuration: exit 0, healthy retry/products PASS, single-movie
  genuine 700/700/refusal PASS, three-movie containment PASS, dataset worker
  exit 1/coordinator exit 3/dataset FAIL/checked cleanup PASS. Every failed movie
  published no product or partial product; no subsequent product kernel dispatch
  was observed. Before/after `nvidia-smi` health checks passed, including no
  surviving compute process and unchanged uncorrected volatile ECC (0).
- Compiled **CUDA detection mutant**, runner line 3703 disabled as described
  above: driver exit 1 at `fatal refusal missing or attributed to the wrong
  movie/patch`, with the genuine 700/700 pair still present. The mutant's healthy
  arm passed and its final GPU health check passed. Source and executable were
  restored byte-for-byte (`mutant-final.json`); no mutant is committed.
- The first mutant probe additionally failed its post-run idle check because
  utilization still sampled 3% from the exited process (no compute process,
  1 MiB memory, ECC 0). Its logs are retained separately as `control-mutant/`,
  `run-mutant.log`, `mutant.json`. The final driver waits at most ten samples for
  that utilization sample to expire, then requires the same zero-utilization
  health criteria. The final rerun has only the intended refusal failure.
- Production `motioncorr` targets built successfully in both configurations;
  symbol/byte audits find no `illegalWrite`, `__wrap_cudaMalloc`,
  `__wrap_cudaLaunchKernel` or `MC_STICKY_FAULT`. Opt-in CUDA/nvCOMP collection
  has 109/112 tests, including exactly one `CudaStickyContext` registration.
  These are collection counts, **not full-suite passes**. The direct driver is
  the registered test command with a retained `--workdir`.

No containment defect was found in this bounded control. Coverage is one early
resident-retry allocation boundary on one A100/driver/toolkit combination,
using a synthetic 512×512×12 uint16 TIFF (the later movies are copies). This
does not establish containment at every CUDA call, genuine nvCOMP-ingest faults,
other GPU architectures/toolkits, or late-product rollback. The dataset control
uses one GPU worker, not multiple simultaneous devices. The compiled mutant was
run on the CUDA configuration only. All existing injected tests are unchanged.

This tests-only change supplies the affected native controls under post-freeze
policy §9.4; no QF rerun is required. Full CPU/CUDA/nvCOMP suites, Tier A,
known-motion/corpus identity, performance and scientific acceptance were not
rerun and retain their earlier source revisions.
