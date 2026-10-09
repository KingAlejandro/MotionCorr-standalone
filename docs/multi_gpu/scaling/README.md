# Dataset-endpoint scaling at a fixed 32-CPU budget

**Result.** End to end (launch of `run_dataset.py` to publication of the joint
STAR and `logfile.pdf`), 4 GPUs × 8 CPUs is 1.34× faster than 1 GPU × 32 CPUs at
24 movies and 1.68× faster at 96 movies. Every paired comparison is resolved
(6/6 pairs faster, CI of the median excludes 0). The worker phase scales 2.8× at
4 GPUs (96 movies). The serial aggregate phase does not scale: it takes ~31 s at
96 movies on every arm. All 36 measured runs passed, and on 24 movies all three
arms are output-identical to a single-process single-GPU run.

Raw data: [`campaign.json`](campaign.json). It holds every run, the host
snapshots, the identity reports and the `paired()` output.

## Results

All values are medians over 6 interleaved reps. `publication` is the timed
quantity. `exit` adds the post-publication integrity and ownership checks
before `run_dataset.py` returns with `dataset_ready`.

| Movies | Arm | Publication s (IQR) | Speedup | Paired diff s (CI 96.9%) | Exit s | Worker phase s | Aggregate phase s | Max idle tail s | Mean cores busy |
|---|---|---|---|---|---|---|---|---|---|
| 24 | 1×32 | 13.87 (0.55) | 1 | — | 16.47 | 8.65 | 7.43 | 0.00 | 1.96 |
| 24 | 2×16 | 11.48 (0.64) | 1.21 | −2.67 (−3.49, −2.12) | 14.25 | 5.42 | 8.33 | 0.18 | 3.47 |
| 24 | 4×8 | 10.37 (0.82) | 1.34 | −4.02 (−4.70, −2.90) | 12.92 | 4.51 | 7.74 | 0.36 | 5.42 |
| 96 | 1×32 | 52.27 (2.21) | 1 | — | 63.17 | 31.02 | 32.40 | 0.00 | 2.07 |
| 96 | 2×16 | 38.17 (1.96) | 1.37 | −13.11 (−16.72, −10.90) | 48.98 | 16.82 | 31.31 | 0.22 | 3.99 |
| 96 | 4×8 | 31.19 (1.31) | 1.68 | −20.62 (−22.84, −19.56) | 41.82 | 11.12 | 30.73 | 0.40 | 7.12 |

Memory:

- **Per-worker RSS high-water mark:** 641-643 MiB in every arm. The median total
  is 642 MiB at 1×32, ~1.28 GiB at 2×16 and ~2.51 GiB at 4×8. The peak
  simultaneous sum of the process tree is lower: 1.1-1.2 GiB at 2×16 and
  2.1-2.2 GiB at 4×8.
- **Sampled peak VRAM:** 3382-3512 MiB per GPU, the same per process in every
  arm. This is a lower bound from `nvidia-smi` sampling, not a high-water mark.

Lock waits were 0 s, and every run's device witness placed each worker PID on
its intended, distinct GPU.

`mean_cores_busy` (2-7 of 32) shows that this workload at `--j 8` does not use
the CPU budget. The 1×32 arm is therefore a fair single-GPU baseline, not a
CPU-starved one.

## Where the serial aggregate time goes

I kept one 96-movie 2×16 run (not part of the campaign) and broke down its
aggregate phase:

- **Staging:** `merge_workers.py` copies 384 staged products (5.2 GB) into
  `merged/`, because `run_dataset.py` does not pass `--link`. (This describes
  `d7339fd`; staging now hardlinks by default, see `../AGGREGATE_STAGING.md`.)
- **Hashing:** it hashes every staged product before the `--aggregate_only`
  binary runs, and again after it, to prove nothing was rewritten. One
  `sha256sum` pass over the tree takes 5.3 s.
- **Aggregate binary:** re-running `--aggregate_only` alone on the kept tree
  took 2.45 s.
- **Timeline:** about 23 s passed between the workers finishing and the joint
  STAR being written, and another 14.7 s between `logfile.pdf` and
  `aggregate.json`.

Most of the serial phase is therefore integrity bookkeeping in Python, not
MotionCorr work. Hardlink staging, a single hash pass taken at worker exit, and
a stat-key after-check now replace it; see `../AGGREGATE_STAGING.md` and the
re-measurement below.

## Identity

The reference is one `motioncorr` process on GPU2 with the same arguments and
`--gpu 0`, written to `ref24/` (rc 0):

```
cd bench-data
flock /tmp/motioncorr-gpu2-correctness.lock env CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 \
  taskset -c 80-87 build-cuda/motioncorr --i movies.star --o ref24/ <worker args> --gpu 0
```

The first measured 24-movie run of each arm was compared with this reference:

- **MRC:** bytes [0:224] and [1024:] compared, which skips the header label
  block that carries the timestamp.
- **STAR:** compared after normalising the output prefix. This covers the joint
  STAR and its row order.
- **`.log`, `.eps`, `.pdf`, `.lst`:** checked for presence.

All three arms were identical: 24 MRC and 25 STAR files compared, 60 files
present, none missing or extra.

A negative control on a copy of the reference caught each fault:

- a flipped MRC byte at offset 5000;
- a swapped joint-STAR row;
- a deleted `.log`.

A flip at offset 300, inside the label block, was correctly ignored.

## Provenance

- **Source:** `d7339fd` (#147 after merging main `9d14275`). The driver is
  `tools/multi_gpu/bench_scaling.py`, run uncommitted at
  sha256 `c8b9df3a…beb16d` and committed unchanged as `fcc2854`. Every tool's
  sha256 is in `campaign.json` → `provenance.tools_sha256`.
- **Binary:** `build-cuda/motioncorr`, Release, sha256 `ae13ab74…85307d`.
- **Statistics:** `paired()` from `stats.py` at `d873993` (sha256 `8d61e054…3c7c`).
- **Inputs:**
  - 24 RELION 3.0 tutorial movies (`20170629_00021` … `00049_frameImage.tiff`).
  - `gain.mrc`, sha256 `8919cdc7…1acd1`.
  - `movies.star` (24 rows), sha256 `fb998f70…0041`.
  - `movies96.star` (96 rows), sha256 `37776885…065a`. It lists each movie
    four times under distinct symlinked names (`r0_` … `r3_`).
- **Worker args:**
  `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --ingest nvcomp`
- **Host:** `4-gpu-vm` with an AMD EPYC 7452, 4× A100 80GB PCIe, driver
  570.86.10, kernel 6.8.0-136, THP `madvise`.
- **Arms**, all with CPU union 72-103:

  | Arm | GPUs | CPU masks |
  |---|---|---|
  | 1×32 | GPU2 | 72-103 |
  | 2×16 | GPU2, GPU3 | 72-87, 88-103 |
  | 4×8 | GPU0, GPU1, GPU2, GPU3 | 72-79, 80-87, 88-95, 96-103 |

- **Locks:** each arm took `/tmp/motioncorr-bench.lock`, then its GPUs'
  `/tmp/motioncorr-gpuN-correctness.lock` in index order. In this campaign the
  locks were held only around measured runs; the four discarded warm-ups ran
  unlocked. The committed driver now locks warm-ups too.
- **Driver command:**

  ```
  taskset -c 119 python bench_scaling.py --binary build-cuda/motioncorr --data bench-data \
    --workload 24=movies.star --workload 96=movies96.star \
    --arm "1x32=$G2@72-103" --arm "2x16=$G2,$G3@72-87;88-103" \
    --arm "4x8=$G0,$G1,$G2,$G3@72-79;80-87;88-95;96-103" \
    --arm-locks ... --reps 6 --stats-lib stats_d873993.py \
    --identity-ref ref24 --identity-workload 24 --out campaign.json -- <worker args>
  ```

  Each run launches:

  ```
  taskset -c 72-103 run_dataset.py --launcher-args="--devices ... --cpus '...' --cpu-budget 32"
  ```

- **Run order:** one discarded warm-up per arm. Arm order rotates every rep, and
  the 24- and 96-movie workloads alternate. The positional (A/B vs B/A)
  breakdown is in each `paired_vs_1x32.positional`.
- **Ignore `provenance.extra.identity_ref_cmd` in the JSON.** It captured the
  wrong line of the reference script. The command above is the one that ran.

## Limitations

- **Shared host.** Load average was 14.7-22.4 throughout. An unpinned foreign
  user's processes were seen on 1-5 of the 32 arm CPUs before and after every
  run; the mean busy fraction of the arm CPUs before a run was at most 0.14. No
  foreign GPU compute processes were seen.
- **The 96-movie workload repeats inputs.** It measures throughput on repeated
  inputs, so page-cache behaviour is not that of 96 distinct movies.
- **All arms use `--j 8`.** The numbers show how the static scheduler scales at
  this worker setting, not the best per-arm tuning.
- **MPS was not run.** #161 measured −7.6% at 4 GPUs. MPS needs its own
  correctness and fault check, and GPU0/1 are shared with other users. The
  scheduler is one process per device by design.
