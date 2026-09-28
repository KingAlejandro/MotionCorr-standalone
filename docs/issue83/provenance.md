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

### Two native allocations, and why

The corrected harness needed a real GPU run. It took two, and the report is
assembled from both, so each section names its own source record.

**Job 3511139** (`gn3000`, exclusive, 13 min) generated its fixtures with the
wrong interpreter. The job script wrote

```sh
module load netcdf4-python/1.7.2-foss-2025a 2>&1 | head -3
```

and `module` is a shell function: the pipe runs it in a subshell, so the
environment change never reached the parent and `/usr/bin/python3` — NumPy
1.22.4 — generated the fixtures. Reproduced directly on the login node: piped,
`python3` resolves to `/usr/bin/python3` with NumPy 1.22.4; unpiped, to the
module's 3.13.1 with NumPy 2.3.1.

The gate caught it inside the job: `verify_fixtures` reported **NOT VERIFIED**,
5 of 5 cases mismatched on both `movie_sha256` and `ground_truth_sha256`, and
exited 1; `ground_truth_mutation` then refused to run at all, because a
`NOT VERIFIED` after its mutation would not have been attributable to the
mutation. Nothing was published from those inputs. What that job does support
is the integrated all-24 screen, which reads the tutorial runroot and not the
known-motion fixtures at all.

**Job 3511154** (`gn3000`, exclusive) reused the first job's binary by digest,
loaded the module without a pipe, and **refuses to generate anything** if the
interpreter is not NumPy 2.x — a wrong toolchain now stops the job rather than
producing inputs nothing downstream could be attributed to. Its fixtures
verified, so the motion-truth and declared-matrix legs come from there.

One further trap, found while fixing this: `tools/run_known_motion_gates.py` is
used exactly as merged, and it defaults `--fixtures` to the repository's own
`test-data/known_motion` and **regenerates in place**. The truth gates
therefore never read the directory `verify_fixtures` had just checked — in job
3511139 that in-place regeneration was the 1.22.4 drift, and it overwrote the
tracked files. Job 3511154 restores `test-data/known_motion` from git first and
then verifies the regenerated copy afterwards (`verify_fixtures_inplace.json`,
**VERIFIED (content)**, 5/5), so the truth verdicts are attributable to the
declared inputs. The merged tool is not modified.

The intervening job **3511145** is preserved because it shows the state that
had to be fixed: its own provenance header opens with six modified files under
`test-data/known_motion`, left behind by 3511139. Its controls passed 10/10,
and it was cancelled during the truth leg once the in-place regeneration was
understood — a verdict computed from that tree would not have been
attributable to anything.

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

### GPU — corrected-harness allocations (`gn3000`)

The runs above predate the harness corrections. The corrected harness was run
on two further dedicated allocations, each `--exclusive` on its own node:

```
sbatch -p gpu --gres=gpu:1 --cpus-per-task=16 --exclusive -t 02:00:00
```

| Item | Value |
|---|---|
| Node | `gn3000.scarf.rl.ac.uk`, allocated **exclusively**, both jobs |
| Devices | 4x NVIDIA A100-SXM4-40GB, driver 580.178.04 |
| Device used | 0 — `GPU-c6c43d6a-aa2e-af46-022c-aa4a4735638d` |
| Other UUIDs on the node | 1 `GPU-2e1b6776…`, 2 `GPU-69bdbeb9…`, 3 `GPU-0ade54fe…`; none used |
| Affinity | `Cpus_allowed_list: 0-63`, `Mems_allowed_list: 0-7` (exclusive node) |
| Node load at start | 3.06, 2.47, 2.75 (3511139) |
| Working tree | `/work4/scd/scarf1415/motioncorr/mc-i83b`, quota-safe project space |
| Tree commit | `7ba584eaf5eae28661d80880fdf220c130c235dc` |
| CUDA binary | `0c5246675175ba4dc52e1c95a99046711a5d67e8e1eb1d829c33fb09e4335b0e` |

| Job | Outcome |
|---|---|
| **3511139** | fixtures NOT VERIFIED (wrong interpreter, see above); **all-24 integrated screen of record**; fixture-dependent legs discarded |
| 3511145 | **cancelled during leg (c)** — started from a tree the previous job had left dirty; superseded by 3511154. Log preserved in `raw/scarf-gn3000-3511154/job-3511145.log` |
| **3511154** | fixtures VERIFIED (content); **motion-truth and declared-matrix legs of record** |

The third VM's GPUs are not involved: nothing in this issue ran outside the
two SCARF allocations above and the cpu64 host. `GPU3`, colleagues' jobs and
the `llama` service were left alone, and the QOS one-running-job cap means the
two jobs above could not have overlapped even had they been submitted together.

Code reached `mc-i83b` as one incremental bundle, verified by digest on arrival
and by `git bundle verify` before `git reset --hard`:

| Bundle | Range | SHA256 | Bytes |
|---|---|---|---|
| `i83-scarf-inc` | `fd1ea50..7ba584e` | `7d9a645332f28a802c54a7fc1648deb244a9e266085c55e591c3f831bbef70af` | 139249 |

The GPU tree therefore sits at `7ba584e`, two commits behind this branch's
head. Both later commits (`89e7a93`, `2a8d13a`) change report rendering and add
pure-Python negative controls; neither touches a runner, a schedule or a gate
that executes on a GPU. Those two controls were asserted on cpu64 at `2a8d13a`
(12 pass / 0 fail), and the GPU records here carry 10 controls for that reason
rather than 12.

Two later cpu64 bundles carried those commits to the CPU host:

| Bundle | Range | SHA256 |
|---|---|---|
| `i83-inc6` | `7ba584e..89e7a93` | `a0b74fc3bd551951d79acf2c9a1a790d81fc5083a8b5f1e77640998c9cf6c208` |
| `i83-inc7` | `89e7a93..2a8d13a` | `662046747c50a3485c6bfb00a8cfaedb9e7715eebdf10e9f4f5de8a5b64802fb` |

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

### CPU — corrected-harness validation

Every harness commit in this series was validated on cpu64 before it was
pushed, under `flock /tmp/motioncorr-issue96-cpu-validation.lock` so it could
not overlap another thread's CPU work.

| Item | Value |
|---|---|
| Host | `small-refmac-machine` (cpu64), 64 logical CPUs |
| Pin | `taskset -c 32-63 numactl --membind=1` |
| Verified placement | `Cpus_allowed_list: 32-63`, `Mems_allowed_list: 0-1` |
| Build/runtime jobs | <= 16 |
| Repository | `/home/ubuntu/mc-i83-cpu` |

The affinity line is measured on a **child launched exactly as the gates
were**, not on the launcher: the launcher shell is deliberately unpinned, so
reading `/proc/self/status` there would have recorded `0-63` and said nothing
about where the work ran. That confusion was itself a defect, fixed at
`025908a` and re-checked in every run since
(`raw/cpu64-705d2c7/gate-child-placement.txt`).

Run of record for the head commit: `raw/cpu64-705d2c7/`, `verify_fixtures`
exit 0 (**VERIFIED (content)**, 4 cases — `km_local_realscale` is not
generated on this host) and `negative_controls` exit 0 with **12 pass /
0 skipped / 0 failed**. The preceding commit's run is preserved beside it in
`raw/cpu64-2a8d13a/`.

| Bundle | Range | SHA256 |
|---|---|---|
| `i83-inc8` | `2a8d13a..705d2c7` | `a46c5334ce97782bd3c3aeca07317b6ceba33bb025e3e9ad571e116a04afadea` |

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

### Corrected harness — what the two `gn3000` jobs ran

Full scripts are preserved alongside the logs. The parts that matter:

```sh
# The fix for the subshell defect: no pipe, and a refusal rather than a
# silently-wrong toolchain.
module load netcdf4-python/1.7.2-foss-2025a
PY=$(command -v python3)
NPV=$("$PY" -c "import numpy; print(numpy.__version__)")
case "$NPV" in 2.*) ;; *) echo "WRONG TOOLCHAIN: numpy $NPV"; exit 2 ;; esac

# The science legs do not run at all if provenance fails, because their
# verdicts would not be attributable to the committed manifest.
"$PY" tools/validation_issue83/verify_fixtures.py \
  --fixtures-dir "$D/fixtures2" --repo "$D" --json "$E/verify_fixtures.json"
rc_verify=$?
[ "$rc_verify" -ne 0 ] && exit 3

# run_known_motion_gates.py regenerates into the repo's tracked fixtures.
# Restore them first; check what it left behind afterwards.
git checkout -- test-data/known_motion
"$PY" tools/run_known_motion_gates.py --binary "$BIN" --gpu 0 \
  --include-heavy --outdir "$E/truth" --json "$E/truth/summary.json"
"$PY" tools/validation_issue83/verify_fixtures.py \
  --fixtures-dir test-data/known_motion --repo "$D" \
  --json "$E/verify_fixtures_inplace.json"
```

CPU, every harness commit, under the shared project lock:

```sh
flock /tmp/motioncorr-issue96-cpu-validation.lock -c '
  taskset -c 32-63 numactl --membind=1 \
    python3 tools/validation_issue83/verify_fixtures.py --fixtures-dir fixtures --repo .
  taskset -c 32-63 numactl --membind=1 \
    python3 tools/validation_issue83/negative_controls.py --fixtures-dir fixtures'
```

## Boundaries observed

No credential change, no new billing account, no install accepting new terms.
No heavy build on a SCARF login node. No production CUDA, runner, CMake or I/O
file modified. No other agent's worktree or process touched.
