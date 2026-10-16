# Reproduction and retained controller

This directory records launchers and the **read-only** result reduction, not an
nvTIFF SDK or a MotionCorr ingest implementation. The exact pre-existing external
harness, native oracle evidence, frozen optimized binaries and loaded libraries
remain on their original hosts; the result receipt binds them by SHA256. Do not
rebuild from current main and label it `6b6adf44`.

## Controller delta and gates

`original_timing_release_20261013.json` records the original controller release.
`timing-release.json` is a **new** release receipt for the retained 13 October
owned-thread departure repair. `observer-lifecycle-only.diff` shows the complete
accounting-module delta: a failed task read can be classified as a departed own
thread only if fresh self-task inventory, self/global TID directories and owner
PID/birth establish departure. Live/reused TIDs, permission/IO errors, identity
and affinity changes still fail. Arithmetic, shorter-wall divisor and the
**0.25 unowned-core limit are unchanged**. No kernel/IRQ CPU is subtracted.

Before timing, both Python modes exercise the actual paired controller and
installed capture adapter (21 tests each), the thread lifecycle (12 tests each),
and an actual Linux counter/child/competitor discriminator (2 controls). The
counter discriminator explicitly uses stand-in GPU receipts, so it is not native
GPU execution or speed evidence. The previous source's failing boundary and
original SCARF attempt are retained separately, never overwritten.

## Launches

VM: a top-level `taskset -c 96-103` shell launches the corresponding numbered
script with `setsid nohup taskset -c 96-103 bash ...`, retaining its PID and log.
Each launcher takes `/tmp/motioncorr-bench.lock` without deleting it, scans for
an old deleted lock inode, records all physical GPUs/processes, and settles on
empty box-wide GPU use, no compiler and load1 < 2 before timing. Builds and
data/oracle work are not run concurrently. No unrelated process is stopped.
Every payload is fresh and bound by explicit UUID; source/input/binary/library
hashes are checked outside timing before and after each row.

- `run-vm.sh`: retained wrapper failure, wrong kit-manifest schema, no movie run.
- `run-vm-2.sh`: corrected exact manifest, retained missing corpus path failure,
  no movie run.
- `run-vm-3.sh`: exact original data-https corpus, first native timed attempt.
- `run-vm-4.sh`: one whole-campaign retry, same settings and unchanged gates.

SCARF: `scarf-timing-20261016.sbatch` was submitted with
`NVTIFF_TIMING_RELEASE_SHA=$(sha256sum timing-release.json | cut -d' ' -f1)`
exported, as job **3633126**. It reserves an exclusive node, uses one A100 UUID
and eight logical threads (four physical cores plus their SMT siblings), runs
the controls and same-allocation native acceptance, then the original 250-row
schedule. Reservation can include more GPUs/CPUs than are actually used; the
resource receipt distinguishes these. A filesystem probe and actual output-file
checks supplement Slurm state. Existing script, source, binary and old failures
are untouched. Shared PanFS storage is not claimed globally dedicated.

## Analysis

Use the preserved `paired.py` for its declared per-file analysis. Then run:

```sh
python3 collect_result.py --run /absolute/path/to/run --out /new/result.json
```

The reducer independently recomputes paired medians and adjacent-null magnitude,
verifies every raw/accounted row hash, changes B−A to positive savings, and
implements `../ANALYSIS_PLAN.md` for the equal-file overall envelope. It never
constructs an overall value for an incomplete campaign. Its synthetic full,
incomplete and receipt-drift controls passed locally; these are not GPU tests.
A driver's `NO_GO_TO_APPLICATION_PILOT` is only a failed GO criterion; the
reducer separates a resolved loss from unresolved variability.

Raw sample dumps/logs stay on hosts. No SDK/header/library is copied into the
repository. No new production dependency, source/default change or licence
compatibility decision is made here.
