# Native two-GPU correctness acceptance (#53), 28 Sep 2026

**Correctness only. No timing, throughput or scaling result appears here**, and
none was measured. #26 owns the performance matrix; per the coordinator, wall
times taken while other work shares this host would be characterization, not
isolated performance. Raw artifacts: [`gpu_evidence/`](gpu_evidence/).

## Allocation actually used

| | |
|---|---|
| Host | `4-gpu-vm`, 124 logical CPUs, 2 NUMA nodes (node 1 = 62-123) |
| Devices | **GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`**, **GPU1 `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`** only |
| CPUs | all MotionCorr descendants inside 96-111 (node 1); build `taskset -c 96-103 -j 8` |
| Worker masks | worker 0 `96-103`, worker 1 `104-111`, disjoint, recorded per worker |
| Per worker | `--j 4 --max_io_threads 4` |
| Mutex | every arm ran under `flock /tmp/motioncorr-bench.lock` |
| GPU3 | untouched. GPU2 was idle when the main arms ran and later held #69's work; recorded, not gated on |

The occupancy gate gates on **GPU0/GPU1 only** and records the other devices.
An earlier version asserted all four idle and aborted the moment #69 started
legitimately on GPU2; that was the harness being wrong, not a conflict.

## Provenance

- Source head **`f433662`**, base `4c952b3f54479653512c4d208e09c9a8c02f3726`,
  staged by `git archive` of the committed tree, `COPYFILE_DISABLE=1`, zero
  AppleDouble files, clean `git status --porcelain`.
- Binary (head) SHA-256 `d4e3afb878eb847ac5ff16c73bfee5295002c126443fa37b663f7174f8d9d258`;
  unpatched-main control `fa26e839300d3213e0418e0eb7ed114b0806e86c2f5850fca5fc11d90136af13`.
- Release, `-DCUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=80`. nvcc 12.8.61, driver
  570.86.10, g++ 13.3.0, cmake 3.28.3, Python 3.12.3, numpy 2.5.3. Zero
  compiler errors.
- Inputs verified against `Movies/SHA256SUMS.txt`: 25/25 OK, `movies.star`
  `fb998f70…`, `gain.mrc` `8919cdc7…`.
- Options, identical in every arm:
  `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --j 4 --max_io_threads 4`,
  plus `--gpu 0` under a per-worker `CUDA_VISIBLE_DEVICES=GPU-<uuid>`.

**A binary-identity note.** The final binary hashes differently from one built
from identical C++ at an earlier staging path: `REPORT_ERROR` and friends embed
`__FILE__`, so 53 absolute source strings differ while the size is byte-for-byte
identical. The harness refused to treat the two as interchangeable and every arm
below was re-run on the one binary above.

## Results

| Arm | Result |
|---|---|
| A0 — device-list witness, unpatched main | `Using CUDA acceleration on GPU device 0`, **exit 0, all 24 movies on one device** |
| A0 — device-list witness, this branch | refused, exit 1, names the 4 requested entries |
| A1 — serial CUDA baseline, 1 GPU | 24/24 movies, 24/24 CUDA stage logs |
| A1b — witnessed single worker | verdict `PASS`, 1 distinct device, 0 unwitnessed |
| C1 — launcher inertness, plain serial vs 1 worker | **24/24 exact PASS** |
| A2 — two workers, two GPUs | verdict `PASS`, **2 distinct devices**, 0 unwitnessed / shared / wrong-device, 36 samples, 12+12 CUDA stage logs |
| A3 — merge | `PASS`, 96 files staged, no lost / duplicate / misrouted / unassigned |
| **C2 — serial vs two-worker sharded, 24 pairs** | **24/24 exact PASS**, `pixel_identical` true, `max_shift_error` 0.0, complete coverage, 24/24 unique report names |
| C3 — aggregate `corrected_micrographs.star` | **identical**, canonical row order, 24 rows |
| A5 — owned-child failure | worker 0 SIGKILLed: rcs `[-9, 0]`, verdict `FAIL`, merge refused; **0 strays, 0 compute apps on owned devices** |
| A6 — non-prefix resume | 17/24 complete at interrupt, canonical indices **5-11 missing**, `IS_PREFIX=0`; both workers resumed; merge `PASS`; **24/24 exact PASS**; aggregate STAR identical |

Per-device witnesses for the two-worker arm, from
`nvidia-smi --query-compute-apps=pid,gpu_uuid` sampled during the run:

```
pid 1211780 -> GPU-eddb42fe-4f9a-adde-76d3-b924e14add54   (mask 96-103)
pid 1211782 -> GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d   (mask 104-111)
```

## What this does and does not establish

**Establishes.** Splitting the 24 tutorial movies across two physical GPUs as
two whole-movie worker processes reproduces the single-GPU CUDA result exactly:
every corrected pixel, full normalized MRC headers, per-frame trajectories,
per-movie STAR fields, and one dataset STAR in canonical input order. It
survives a killed worker and a genuinely non-prefix resume. Both devices were
witnessed by physical UUID, not inferred from an ordinal.

**Does not establish.** No throughput, latency, memory or scaling claim — none
was measured. One dataset, one geometry, one frame count, one option set, two
GPUs. `--grouping_for_ps`, `--even_odd_split`, EER inputs, gain rotation/flip
and >2 devices are unrun. `logfile.pdf` equivalence is excluded by construction.
CPU/RELION Gate 2 is untouched and remains separately failing.

## Failures and corrections during this session, kept

Four arms were aborted or invalidated by defects in the harness or the tooling.
All are retained rather than quietly re-run.

1. **`Sampler._stop` shadowed `threading.Thread._stop`.** The first native
   two-GPU run processed all 24 movies correctly and then died in teardown with
   `TypeError: 'Event' object is not callable`, discarding `status.json` and the
   device witness. Fixed in `09fa3d8`; no CPU test could reach it, because the
   sampler only starts with `--devices`.
2. **The serial baseline ran on CPU.** `--gpu 0` was missing from the shared
   option string while the launcher injects it per worker, so the first
   comparison was CPU-serial against CUDA-sharded — the separately tracked
   Gate 2 divergence, `max_shift_error` 0.0064 px, 0/24. The comparator failed
   closed rather than reporting parity. The CPU arm is retained on the host as
   `serialF_cpu_mislabelled`.
3. **The occupancy gate asserted all four GPUs idle**, aborting when #69 started
   on GPU2 under the parallel-work authorization. Now scoped to owned devices.
4. **The resumed merge failed on a harness artifact**: the harness wrote
   `resume.log` into each worker directory and the merge refused a file no movie
   explains. That guard is correct — an unexplained file in a worker directory
   is what a misroute looks like — so the log was moved out rather than the
   guard loosened.
