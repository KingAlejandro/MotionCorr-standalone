# GPU sharing: several processes per GPU, and NVIDIA MPS

Evidence record so this need not be re-measured from scratch. Nothing here
changes the program. Related: #53 (multi-GPU), #157 (single-GPU overheads).

## Conclusions

1. **More MotionCorr processes on one GPU do not raise that GPU's throughput.**
   Co-resident processes contend on the device, and each one roughly doubles
   its own per-movie wall time (section C).
2. **CUDA context creation serialises across processes on one host,
   whichever GPU they use** (section A). One process pays about 255 ms; four
   concurrent processes pay about 863 ms each. Sharing one GPU makes no
   difference to this, and persistence mode did not help.
3. **MPS is a small multi-GPU start-up lever, not a throughput lever.** With
   one process per GPU, MPS cut the 24-movie wall by 0.4% (1 GPU), 1.4%
   (2 GPUs) and 7.6% (4 GPUs). The saving matches cheaper, shared context
   creation, and it shrinks as datasets grow (section B).
4. **MPS correctness and fault isolation are untested.** The campaign script
   stopped before its product and fault checks. MPS clients share one GPU
   context, so a fatal fault in one can affect the others. MotionCorr's
   fail-closed CUDA ownership (#69) was designed per process, so any MPS
   adoption needs its own checks.

Single-GPU speed therefore has to come from removing serial dependencies
inside one process (#159 and the follow-ups in #157).

## A. CUDA context creation and teardown (30 Sep–1 Oct, 4GPUs VM)

The probe is `evidence/cuda_init_probe.cu`, a standalone program with no
MotionCorr code. It times context creation, the first 57 MB allocation, the
first kernel, and the first and second 3710×3838 R2C plans. The analysis is in
`evidence/SETUP_ATTRIBUTION_post128.md`, from the unmerged branch
`experiment/post128-multigpu`. That branch's last local commit `0b364f5`,
which adds the teardown and pinned-memory stages, is reproduced here because
it was never pushed.

| concurrent processes | context creation | vs 1 |
|---:|---:|---:|
| 1 | 254.7 ms | ×1.00 |
| 2 | 432.4 ms | ×1.70 |
| 3 | 636.0 ms | ×2.50 |
| 4 | 862.6 ms | ×3.39 |

- Four processes on **one** GPU cost ×3.02, statistically the same as four
  different GPUs (×3.39). The cost is driver- or host-global, not per device.
- Persistence mode: 254.7 → 251.1 ms (1 process) and 862.6 → 861.6 ms
  (4 processes). No effect. Raw samples are in `evidence/probe_persistence_off.txt`
  and `evidence/probe_persistence_on.txt`.
- Teardown is not explicit in MotionCorr; it runs at process exit, inside the
  measured wall. It costs 345 ms at 4 workers and serialises at about +84 ms per
  worker (commit `0b364f5`).
- Inside the application, a 1-GPU run pays a first-movie warm-up of 0.40 s over
  the steady movie.

## B. MPS campaign (1 Oct, 4GPUs VM)

### B1. Probe under a user-scoped MPS daemon

The probe is `evidence/initprobe_mps.cu`, the same probe extended with pinned
allocation and free, plan release, and context destroy. The log is
`evidence/mps_probe_20261001.log`. Medians exclude round 1, which includes
daemon warm-up (n=1 then took 885 ms).

| concurrent processes | context (MPS) | context (no MPS, section A) | context destroy (MPS) | probe total (MPS) |
|---:|---:|---:|---:|---:|
| 1 | 170 ms | 255 ms | 68 ms | 443 ms |
| 2 | 286 ms | 432 ms | 123 ms | 619 ms |
| 3 | 452 ms | 636 ms | 162 ms | 838 ms |
| 4 | 569 ms | 863 ms | 207 ms | 1008 ms |

Pinned allocation of about 145 ms per process is not affected by MPS.

### B2. Application timing, one process per GPU

- Script: `evidence/mps_campaign_20261001.sh`. Log: `evidence/mps_campaign_20261001.log`.
- Harness: `tools/multi_gpu/run_multi_gpu.py` from the static-worker branch.
- Binary built from `098b4bd`. Input: the 24-movie tutorial, 32-CPU budget,
  5 interleaved reps per arm, MPS off for all reps and then on.
- Every run: rc 0, verdict PASS, 24 MRCs.

| GPUs | MPS off (5 reps) | MPS on (5 reps) | median Δ |
|---:|---|---|---|
| 1 | 13.121, 12.890, 13.094, 12.814, 12.965 | 12.983, 12.789, 12.914, 12.817, 12.959 | −0.051 s (−0.4%) |
| 2 | 7.468, 7.361, 7.401, 7.422, 7.322 | 7.312, 7.211, 7.296, 7.499, 7.206 | −0.105 s (−1.4%) |
| 4 | 5.207, 5.258, 5.483, 5.531, 5.218 | 4.746, 4.821, 4.903, 4.858, 4.888 | −0.400 s (−7.6%) |

### B3. Not run

The script stopped on a shell syntax error (`$(date ... .%N)` split across
lines) right after the timing block. These steps never ran:

- product equality under MPS;
- cross-client fault isolation;
- per-client memory accounting.

`evidence/mps_campaign_last_shard_20261001.out` is the last 2-worker shard
report written before the stop.

### B4. Operational notes from the script

- Start a **user-scoped** daemon with `CUDA_MPS_PIPE_DIRECTORY` and
  `CUDA_MPS_LOG_DIRECTORY` under `/tmp`.
- Launch it with `3>&-`. `nvidia-cuda-mps-control -d` daemonises and inherits
  every open fd, including a `flock` fd, so without it the bench lock stays held
  after the script exits.
- Warm the server on each device before timing.
- Always shut down with `echo quit | nvidia-cuda-mps-control`.
- MPS needs compute mode Default or Exclusive-Process. All four GPUs were Default.

## C. Two processes on the same GPU (8 Oct, 4GPUs VM, GPU0)

- Script: `evidence/same_gpu_two_workers_20261008.sh`.
- Binary: current main `9d14275` (#154 + #155).
- Input: the 24-movie tutorial, nvCOMP ingest, 5 rounds with arm order
  alternated. Host load1 was 7.8–12.6, from another user's CPU jobs.
- The two-process arms split the movie list into alternating halves of 12.

| arm | CPUs | wall s (5 rounds) |
|---|---|---|
| 1 process, `--j 8` | 96–103 | 8.49, 8.38, 8.30, 8.37, 8.44 |
| 2 processes, same GPU, `--j 4` each | 96–99 / 100–103 | 8.37, 9.12, 8.44, 8.38, 8.59 |
| 2 processes, same GPU, `--j 8` each (16 CPUs) | 96–103 / 104–111 | 8.62, 8.70, 8.33, 7.44, 8.46 |

- Union of the halves vs the single run: 24 MRC payloads, 0 differ.
- Sum of per-movie walls: one process, 24 movies 7.22 s. Two co-resident
  processes: 12 movies 6.41 s and 6.82 s each.
- This is the "C2, same physical GPU" arm proposed in
  `docs/multi_gpu/SCALING_EXPERIMENT.md` on `integrate/pr106-issue53-static-workers`.
  That arm was previously run only for correctness (24/24 exact).

## If revisiting

- **MPS for multi-GPU start-up:** finish B3 first, then time through the
  complete dataset endpoint (#147), not launcher wall.
- **Same-GPU co-residency:** re-test only if per-process work becomes
  host-bound with long GPU-idle gaps, and confirm the gaps with `--profile`
  plus Nsight first. Today the processes contend on the device instead.
- **Cheaper context cost without MPS:** a single process driving several
  GPUs, or one long-lived worker per GPU, avoids repeated context creation.
  This overlaps the worker-lifetime pooling evidence in #136/#140.
