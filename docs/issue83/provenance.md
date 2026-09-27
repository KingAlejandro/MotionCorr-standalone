# Issue 83 — provenance

Everything needed to replay the recorded results: hosts, devices, load,
affinity, and source, binary, harness and input hashes.

## Repository

| Item | Value |
|---|---|
| Branch | `opus/issue-83-headless-20260927` |
| Start commit | `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` (verified) |
| Base update | none taken — `origin/main` was at the same `1d7e13f`; `origin/integrate/cuda-stabilization` at `9154b68` is an ancestor |
| Worktrees | one; no other checkout created or modified |

SCARF has no outbound access to GitHub, so commits reach it as git bundles
whose sha256 is verified on arrival, and by `git bundle verify`, before
`git reset --hard`:

| Bundle | SHA256 | Applied to |
|---|---|---|
| harness fixes | `02a4e01fa650422236d04ccbee46e78a35130f05090db849ace7226a425ccb13` | SCARF |
| `..0a6dbff` | `03adbce2eb7d5fb28eb04efa44b781cadd60b7c890bff071c2ece2739072a411` | SCARF |
| `0a6dbff..d48d875` | `3cbedeb8ac788af6a249741569b38048f8913c996c59d469752aaba9061d6147` | SCARF |
| `bab9f46..d48d875` | `23bc705d68aad844835b433f6653708b22f1967301ab168309f4a90604fc6cb8` | cpu64 |

Each hash was compared against the locally computed one before the fetch, and
each bundle's required base ref was confirmed present in the target tree.

## Inputs

Known-motion fixtures are generated, never committed:

```sh
python3 test-data/generate_known_motion_fixture.py --outdir <FIX> --include-heavy
```

### Correction — an earlier revision of this file overstated this check

An earlier revision of this document claimed every generated `.mrcs` "matched"
`test-data/known_motion/MANIFEST.json` and listed the SCARF hashes below as
evidence. **That claim was wrong**, and the table it rested on was not a
comparison against the committed manifest at all.

The generator writes a fresh `MANIFEST.json` into its own output directory, so
a manifest found next to the fixtures agrees with them by construction. Both
hosts did exactly that, each agreed with itself, and a real divergence went
unnoticed until the manifest tracked in git was read directly:

| Host | Python / NumPy | `km_global_hisnr.mrcs` | vs committed manifest |
|---|---|---|---|
| cpu64 | 3.12.3 / 2.5.3 (venv), 1.26.4 (system) | `f9da4668...` | **match** |
| SCARF `gn0005` | 3.9.25 / **1.22.4** | `4e8666c1...` | **mismatch** |

All five cases diverged on SCARF. Regenerating there under
`netcdf4-python/1.7.2-foss-2025a` (Python 3.13.1, NumPy 2.3.1) reproduces the
committed hashes exactly, so the cause is the NumPy 1.22 versus 2.x arithmetic
the manifest's own note warns about -- not a corrupted checkout.

The committed, declared values are:

| Fixture | Declared SHA256 | Bytes |
|---|---|---|
| `km_global_hisnr.mrcs` | `f9da46682b8466c70c6d8814ca944ae073f8fd4f20d040efc490963f648ad990` | 12583936 |
| `km_local_hisnr.mrcs` | `2ae3c87938545aafae71e3e51d7f9040e8f3de6e1cd8a1f14e1c27980272d092` | 12583936 |
| `km_local_noisy.mrcs` | `98930a070a9da7b172c940a2e6bcf95044dcd2070f4637dba2e8b3635ac6a668` | 12583936 |
| `km_local_nonsquare.mrcs` | `9ef410b8cf70bfafddd1659bfc3fae5c17ef802ea57d301f93434f1f89a598d8` | 18875392 |
| `km_local_realscale.mrcs` | `886b277be567e8ae310f3ec3b7bca95cb4e1776a71217e862e9abe0ef162abf7` | 402654208 |

`tools/validation_issue83/verify_fixtures.py` now reads the manifest from git
and fails on mismatch. Its two controls: cpu64 `VERIFIED`, SCARF-as-generated
`NOT VERIFIED` on all five cases. Every GPU result published here comes from a
run whose fixtures passed that check; superseded runs on the drifted fixtures
are listed as such in `progress.md` and their verdicts are not carried forward.

The generator's self-rewriting manifest is flagged independently in review on
PR #82 (`test-data/generate_known_motion_fixture.py:489`). Fixing the generator
belongs there; this issue only adds a read-only check.

The all-24 leg reads the standard tutorial runroot (24 movies, `movies.star`).

## Binaries

| Backend | SHA256 |
|---|---|
| CUDA `build-cuda/motioncorr` (Release, sm80, CUDA 12.8, TIMING=ON) | `3860bce6165974b9c95f982ce670915d5514c1129aaf80beb2c91462aaec4437` |
| CPU `build-cpu/motioncorr` (Release) | `90d683dd0e406d2d8feeea39051557fb15eac0045fa0aae9af8347ada11ac5e4` |

## Harness and comparator

Recorded in every report's `provenance` block. At the time of the runs:

| File | SHA256 |
|---|---|
| `tools/compare_motioncorr.py` (merged, unchanged) | `cb37991af515c5529f31ac48adb157771b1ac21b8308ba28735362f36085e46b` |

The comparator and `tools/run_known_motion_gates.py` are used exactly as
merged. No threshold, profile or verdict in either was modified.

## Compute

### GPU — primary, dedicated allocation

```
sbatch -p gpu --gres=gpu:1 --cpus-per-task=8 --exclusive -t 03:00:00
```

| Item | Value |
|---|---|
| Node | `gn0005.scarf.rl.ac.uk`, allocated **exclusively** |
| Devices | 4x NVIDIA A100-SXM4-40GB, driver 580.178.04 |
| Device used | 0 |
| Toolkit | nvcc release 12.8, V12.8.61 |
| Affinity | `Cpus_allowed_list: 0-63` (exclusive node) |
| Node load at start | 0.52, 0.74, 0.39 |
| Working tree | `/scratch/scarf1415/mc-i83-tree` |

Jobs of record: **3510290** (matrix + all-24 + report, at `d48d875`) and
**3510288** (capacity datapoint + `realscale_local`, at `0a6dbff`).

No allocation was shared at any point. Other jobs on this shared account —
3510270, #74's `mc-i74` (3510287) and `mcks` (3510289) — ran on different
nodes (`gn3000`) or partitions; every job here requested `--exclusive` and
received its own node. The shared 4GPUs fallback was **not used**, and no
benchmark ever ran concurrently with another thread's on the same allocation.

### CPU — separate diagnostic verdict

| Item | Value |
|---|---|
| Host | `small-refmac-machine` (cpu64), 64 logical CPUs |
| Affinity | `taskset -c 56-63` — verified `Cpus_allowed_list: 56-63` |
| Threads | `--j 8`, `OMP_NUM_THREADS=8`, BLAS pinned to 1 |
| Load at start | 3.05, 3.01, 2.76 |

Issue **#73**'s EER pilot holds CPUs 48-55 on this host. This run uses a
**disjoint** mask so the two never share cores. No other user's processes were
inspected beyond identifying that conflict, and none were altered.

## Exact commands

```sh
# Small declared matrix, native CUDA
python3 -u tools/validation_issue83/run_matrix.py \
  --binary build-cuda/motioncorr --gpu 0 \
  --fixtures-dir fixtures --outdir evidence3/matrix \
  --include-heavy --json evidence3/matrix/summary.json

# All-24 tutorial schedule equality
python3 -u tools/validation_issue83/run_all24_schedules.py \
  --binary build-cuda/motioncorr --gpu 0 \
  --runroot <RUNROOT> --outdir evidence3/all24 \
  --json evidence3/all24/summary.json

# CPU-backend diagnostic (no --gpu: a CUDA marker here is an error)
python3 -u tools/validation_issue83/run_matrix.py \
  --binary build-cpu/motioncorr \
  --fixtures-dir fixtures --outdir evidence3/matrix-cpu \
  --json evidence3/matrix-cpu/summary.json

# One measured capacity datapoint, sampled from the driver while the
# largest declared row runs. Not a sweep and not a fallback claim.
python3 -u tools/validation_issue83/measure_capacity.py \
  --device 0 --interval 0.5 --label realscale_local \
  --note "2048x2048, 24 frames, local 5x5 patches, native CUDA" \
  --json evidence3/capacity.json \
  -- python3 -u tools/validation_issue83/run_matrix.py \
       --binary build-cuda/motioncorr --gpu 0 \
       --fixtures-dir fixtures --outdir evidence3/matrix-realscale \
       --include-heavy --rows realscale_local \
       --json evidence3/matrix-realscale/summary.json

# Compact report
python3 tools/validation_issue83/report.py \
  --matrix-json evidence4/matrix/summary.json \
  --all24-json evidence4/all24/summary.json \
  --truth-json evidence/truth/summary.json \
  --cpu-diagnostic-json evidence4/matrix-cpu/summary.json \
  --capacity-json evidence3/capacity.json \
  --out docs/issue83/support-report.md
```

The matrix, all-24 and CPU legs of record were all run at `d48d875`, so the
published table comes from a single harness revision. The `evidence3` paths
above are the earlier run; only `capacity.json` is carried forward from it,
and it measures the driver rather than the harness.

## Boundaries observed

No credential change, no new billing account, no install accepting new terms.
No heavy build on a SCARF login node. No production CUDA, runner, CMake or I/O
file modified. No other agent's worktree or process touched.
