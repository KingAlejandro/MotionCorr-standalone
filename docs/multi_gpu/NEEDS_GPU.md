# NEEDS_GPU — #53 native serial-vs-sharded equality and device witnesses

**Status: requested, not scheduled, UNRUN.** Nothing in this file has been
executed. No result below is claimed. #26 owns this round's initial GPU slot;
this request waits for Codex monitoring to assign one.

## Purpose

**Correctness only. There is no timing arm and no benchmark matrix here.** The
question is whether running the 24 tutorial movies as N disjoint shards across
N physical GPUs produces bit-identical per-movie outputs to the serial
single-GPU run, and whether the devices claimed were the devices used.

## Resources requested

Per the resource update of 28 Sep 2026 and `COMMON.md`:

- Shared `4GPUs` (`4-gpu-vm`), **initially at most 2 available GPUs**; the same
  protocol extends to 4 if more are released.
- Aggregate **16 logical CPUs, 96-111, NUMA node 1**, across all MotionCorr work.
- One `flock /tmp/motioncorr-bench.lock` held for the whole session; holder
  identity in `/tmp/motioncorr-gpu-timing.lock`.
- A dedicated SCARF Slurm allocation is preferred if offered; scratch under a
  writable account-specific `/work4/scd` path after a space and quota check,
  moving no existing directory.
- Estimated occupancy: one serial arm, one sharded arm, 24 comparator
  invocations, plus the two argument-parser probes. No repeats, because nothing
  is being timed.

## Inputs to pin before submission

- Source SHA and a clean `git status --porcelain` in every tree used.
- Binary SHA-256, `CMAKE_BUILD_TYPE=Release`, CUDA toolkit and driver versions,
  `CMAKE_CUDA_ARCHITECTURES`.
- `movies.star` `fb998f70…` and `gain.mrc` `8919cdc7…`, verified against
  `Movies/SHA256SUMS.txt`.
- For every run: chosen cores, the inherited cpuset, CPU/NUMA/memory policy,
  and the actual GPU UUIDs, as the resource update requires.
- `nvidia-smi` idle baseline for every device touched, and host load average at
  start.

## Arms

### A0 — argument-parser witness on a CUDA build

The one claim PR A's CPU evidence cannot support. Two commands, no dataset, no
CUDA context beyond a device count:

```bash
# unpatched main 4c952b3f, CUDA build: expected to print
#   "Using CUDA acceleration on GPU device 0"
# i.e. four devices requested, one silently used.
<base-bin>  --i movies.star --o /tmp/probe_base/  --use_own --gpu 0:1:2:3 --j 1

# this branch, CUDA build: expected to refuse, naming 4 requested entries.
<head-bin>  --i movies.star --o /tmp/probe_head/  --use_own --gpu 0:1:2:3 --j 1
```

### A1 — serial single-GPU baseline

```bash
CUDA_VISIBLE_DEVICES=<uuid0> taskset -c 96-111 <head-bin> \
    --i movies.star --o serial/ --use_own --gpu 0 --j 8 <dataset options>
```

### A2 — sharded run, one worker per physical GPU

```bash
python3 tools/multi_gpu/run_multi_gpu.py \
    --star movies.star --out sharded/ --binary <head-bin> \
    --devices <uuid0>,<uuid1> --cpus 96-111 \
    -- --use_own --j 8 <same dataset options>
```

`status.json` must report `verdict: PASS`, every worker exit `0`, and a
`gpu_witness` block with
`all_pids_witnessed_on_intended_distinct_devices: true`,
`distinct_devices_witnessed` equal to the worker count, and an empty
`unwitnessed_pids`. A worker never seen holding a context is reported as
unwitnessed, not as a pass.

Aggregate CPU budget note: with 16 logical CPUs and 2 workers, `--j 8` per
worker saturates the allocation exactly. The old shared-VM study ran `--j 8`
per worker inside an eight-CPU mask, i.e. 4x oversubscribed; that is a plausible
cause of its slowdown and has never been tested by intervention. PR A does not
test it either — it is a #26 question.

### A3 — merge and deterministic aggregation

```bash
python3 tools/multi_gpu/merge_workers.py \
    --manifest sharded/shards/shard_manifest.json \
    --workers sharded/w0 sharded/w1 --status sharded/status.json \
    --out merged/ --report merge_report.json \
    --aggregate-with <head-bin> --input-star movies.star \
    --aggregate-args -- --use_own --j 8 <same dataset options>
```

Required: `verdict: PASS`, 24 movies, no lost/duplicate/misrouted/unassigned
entry, and `aggregate_star.row_order == "canonical"`.

### A4 — exact per-movie equality, 24 invocations

```bash
python3 tools/multi_gpu/compare24.py \
    --ref serial/ --test merged/ --tool tools/compare_motioncorr.py \
    --manifest sharded/shards/shard_manifest.json --out exact/
```

Required: 24/24 with `pixel_identical`, complete coverage, and the trajectory
and STAR checks each passed. A `PASS` overall status alone is not accepted.

### A5 — resume and killed-worker controls on real data

Kill one worker after roughly half its shard, confirm the merge refuses to
publish, resume with `--only_do_unfinished`, then re-run A3 and A4 and require
the same verdicts against the A1 baseline.

## Retention

Both arms' complete output trees are retained, not just the comparator reports.
A parity run against a different arm cannot certify an arm whose outputs were
deleted — that is exactly how the historical four-GPU SCARF series lost its
timed arms.

## Explicitly excluded

- Any timing, throughput or scaling number. #26 owns that.
- `logfile.pdf` equivalence. Path-dependent by construction; asserted present
  and non-empty at most.
- CPU/RELION Gate 2. A separate, currently failing, verdict that this work must
  not move in either direction.
