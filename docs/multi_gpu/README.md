# Static multi-GPU whole-movie scheduling (#53), PR A

Design and changed-file whitelist: [`agents/designs/issue_53_multi_gpu_scheduling.md`](../../agents/designs/issue_53_multi_gpu_scheduling.md).

PR A refreshes the #53 launcher concept onto current main, makes the native
device-list behaviour honest, and proves the scheduling failure modes on CPU.
**It makes no throughput, memory or numerical claim.**

The native two-GPU correctness arm has since been **run and passed** under a
coordinated slot: see [`GPU_ACCEPTANCE.md`](GPU_ACCEPTANCE.md).
[`NEEDS_GPU.md`](NEEDS_GPU.md) is retained as the request that arm was executed
against, not as an outstanding ask.

## What is here

| File | Role |
|---|---|
| `tools/multi_gpu/star_io.py` | STAR reader mirroring the C++ reader's observable semantics |
| `tools/multi_gpu/partition_star.py` | disjoint shards from original row bytes, with collision preflight |
| `tools/multi_gpu/run_multi_gpu.py` | one stock process per physical GPU, UUID-pinned, with device witnessing |
| `tools/multi_gpu/merge_workers.py` | staging plus lost/duplicate/misrouted/failed detection, deterministic order |
| `tools/multi_gpu/gpu_witness.py` | UUID selection and `nvidia-smi` compute-apps witnesses |
| `tools/multi_gpu/compare24.py` | per-movie exact comparison against a serial baseline |
| `tests/test_multi_gpu_scheduling.py` | 38 CPU-only cases, registered as the `MultiGpuScheduling` CTest |
| `tests/fake_worker.py` | binary stand-in with fault injection |
| `docs/multi_gpu/negative_controls.py` | 45 mutation entries, each required to break its case |

## Usage

```bash
# one worker per physical GPU, distinct output directories
python3 tools/multi_gpu/run_multi_gpu.py \
    --star movies.star --out run/ --binary build/motioncorr \
    --devices 0,1 --cpus 96-111 \
    -- --use_own --j 8 --dose_weighting --angpix 0.885

# stage, verify, and regenerate the dataset STAR with the stock binary
python3 tools/multi_gpu/merge_workers.py \
    --manifest run/shards/shard_manifest.json \
    --workers run/w0 run/w1 --status run/status.json \
    --out run/merged --report run/merge_report.json \
    --aggregate-with build/motioncorr --input-star movies.star \
    --aggregate-args='--use_own --j 8 --dose_weighting --angpix 0.885'
```

Note the `=` form on `--aggregate-args`: without it argparse reads the leading
dash as the next option.

## Verified on CPU, 2026-09-28

Everything below comes from one run, recorded in
[`pr_a_evidence/cpu64_validate.log`](pr_a_evidence/cpu64_validate.log).

**Provenance** ([`pr_a_evidence/source_provenance.txt`](pr_a_evidence/source_provenance.txt),
echoed at the top of the validation log): source head
`bceb30e058238aa51c7edd0eb597fbabb8cfc6b0`, base
`4c952b3f54479653512c4d208e09c9a8c02f3726`, staged by `git archive` of the
**committed** tree with `COPYFILE_DISABLE=1`. The harness asserts the staged
tree contains zero macOS AppleDouble `._*` files and aborts otherwise
(`applefile_count=0`), and it aborts on a failed configure or build rather than
proceeding to test a stale artifact. `BUILD_RC=0` with zero compiler `error:`
lines.

Host `small-refmac-machine` (cpu64), `taskset -c 32-63` (NUMA node 1), under
`flock /tmp/motioncorr-issue96-cpu-validation.lock`. Release,
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`; g++ 13.3.0, cmake 4.4.3, Python 3.12.3.
Patched binary SHA-256 `f4748106a1a296efd961b655fce675c9336cda42ca63f7b4bf4488d12ef9e8f2`;
unpatched-main control binary `de35fddc37d8237576adea7d34bec618ce1bf4867286b87ec568815c71645f8a`.

| Layer | Result |
|---|---|
| `tests/test_multi_gpu_scheduling.py --binary <built>` | **39/39 passed** |
| `docs/multi_gpu/negative_controls.py` | **all attempted mutations detected**, no survivors (see note below) |
| `ctest --output-on-failure -j 4` | **14/14 passed** — the 13 pre-existing CPU tests plus `MultiGpuScheduling` |
| end-to-end: real binary, serial vs 3-way sharded | **6/6 movies exact**, merge `PASS`, aggregate STAR identical |

### The end-to-end arm

This is the CPU analogue of the unrun CUDA arm, run with the real binary rather
than the fake worker. Six movies over three worker processes with distinct
output directories, then merge, then per-movie comparison against a serial run
of the same six. Artifacts:
[`e2e_shard_manifest.json`](pr_a_evidence/e2e_shard_manifest.json),
[`e2e_launcher_status.json`](pr_a_evidence/e2e_launcher_status.json),
[`e2e_merge_report.json`](pr_a_evidence/e2e_merge_report.json),
[`e2e_exact_summary.json`](pr_a_evidence/e2e_exact_summary.json).

- `tools/compare_motioncorr.py --gate exact`, one invocation per movie: **6/6**
  pixel-identical with complete coverage and the trajectory and STAR checks each
  passed. A `PASS` overall status alone is not accepted.
- Merge `verdict: PASS`, `launcher_verdict: PASS`, 24 files staged, no lost,
  duplicate, misrouted or unassigned entry.
- The aggregate `corrected_micrographs.star` regenerated over the merged tree is
  **byte-identical** to the serial run's once the output directory prefix is
  normalised (`AGGREGATE_STAR_IDENTICAL=1`), in canonical input row order.

**Why this comparison is not vacuous.** The six movies are one synthetic TIFF
symlinked six times, so identical metadata handling would make all six outputs
byte-identical and an exact comparison would prove nothing. The fixture gives
each movie a distinct pre-exposure and splits them across two optics groups with
different pixel sizes and voltages, and the run records
`DISTINCT_PAYLOADS=6/6` — all six corrected images differ. Per-movie optics and
exposure therefore demonstrably reach each movie, and the serial-versus-sharded
equality is a real check on the partitioning.

**What it does not cover.** One movie shape, one frame count, CPU backend only,
`--j 4`, no gain reference, no `--only_do_unfinished` across a real interrupted
run. The killed-worker and non-prefix-resume cases are exercised against the
fake worker, not the real binary.

### Recorded interference

`cpu64` was busy throughout: load average `40.52 22.97 13.09` at start and
`51.49 29.74 16.02` at end, with a concurrent `python` at 5656% CPU, another
round's `motioncorr` at 373%, and two `ctffind` process trees (PIDs
1156938/1156942 and 1635423/1635428/1635429, each `OMP_NUM_THREADS=1 -j:1`) —
all captured in the `INTERFERENCE AT START` / `AT END` sections of the
validation log. This run holds the validation lock and is confined to cores
32-63.

None of this affects any claim here, because **nothing in PR A is timed**. It is
recorded because the round requires it, and so that none of this evidence is
ever reused as a timing baseline.

## Device-list behaviour, before and after

Transcript in the `DEVICE LIST` section of the validation log.

| `--gpu` | unpatched main `4c952b3f` | this branch |
|---|---|---|
| `0:1:2:3` | generic "built without CUDA support" | echoes the spec, reports 4 requested entries, refuses |
| `0,1` | generic | echoes the spec, reports 2 requested entries, refuses |
| `0:1` | generic | echoes the spec, reports 2 requested entries, refuses |
| `0abc` | generic | "not a non-negative device id" |
| `-1` | generic | "not a non-negative device id" |
| `0` | generic | generic — unchanged, correctly |

A trailing colon (`--gpu 0:`) is reported as two device entries, the second
empty. That is deliberate: it is two colon-separated fields, and `--use_own`
accepts one.

### What this evidence shows

On a **CPU-only** build the list syntax is rejected *as a list*, with the spec
echoed and the count named, where before it produced only the generic
missing-CUDA message. The syntax check sits outside `#if defined _CUDA_ENABLED`
so this is observable without a GPU.

The behaviour the change exists to stop is **no longer a code-reading claim**.
It was witnessed on a CUDA build and is recorded in
[`GPU_ACCEPTANCE.md`](GPU_ACCEPTANCE.md): unpatched main given `--gpu 0:1:2:3`
printed `Using CUDA acceleration on GPU device 0`, exited 0, and processed all
24 movies on a single device — 24 corrected MRCs and 24 per-movie CUDA profile
markers.

## Negative controls

`negative_controls.py` holds 45 mutation entries. It applies them one at a time
to a scratch copy and requires the corresponding cases to fail. An entry whose
case needs a tool the host lacks is reported SKIPPED and explicitly not counted
as detected, so the printed figure is detected-over-attempted, not
detected-over-entries: **45/45 on Linux with `taskset`**, 44/45 attempted on
macOS. No mutation survives
([`negative_controls.json`](pr_a_evidence/negative_controls.json)). That covers
every Python-side guard. The one guard outside its reach is the C++ device-list
rejection, because mutating it needs a rebuild; its control is the recorded
unpatched-main binary, which produces a different message for the same input.

## Deliberate non-claims

- **No speedup, and no benchmark.** `run_multi_gpu.py` records a wall time for
  bookkeeping and says in its own status file that it is not a measurement.
  #26 owns this round's matrix. Historical four-GPU SCARF figures on source
  `0c7d68f` are not a current-main scaling curve and are not repeated here.
- **No `logfile.pdf` equivalence.** The PDF batch loop globs only the current
  pending list, so a partitioned or resumed run's PDF differs from a serial
  run's by construction. Nothing here produces one or compares one. The
  end-to-end run also reproduced the known ghostscript `batch.pdf` failure,
  which is a pre-existing, separately tracked observation.
- **No numerical claim.** PR A changes no numerical result. The historical
  CPU/RELION Gate 2 failures and the noisy-truth characterisation failures are
  untouched and remain separate verdicts.
- **One worker per GPU is the first experiment**, not a claimed optimum, and
  whole-movie granularity is a scheduling decision, not a proof that intra-movie
  multi-GPU is impossible. That is deferred.

## Disposition of PR55's prototype and its review

PR55 (`t3code/issue53-movie-scheduling` @ `377cb30`) received its own Codex
review. That branch, its history and its evidence are untouched by this PR; the
four files here are a fresh port onto current main, not a rebase of it. Its
three findings map as follows.

| PR55 finding | Status here |
|---|---|
| [`r4119254841`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/55#discussion_r4119254841) — `compare24.py` writes one report path for two movies sharing a basename, so `--reuse` can turn a failed comparison into a false 24/24 pass | **Fixed.** The same defect was raised on this PR as `r4119223242`. Reports are keyed by the complete output root; `case_compare24_report_identity` orders a fail-then-pass pair so a basename collision would launder the failure, and checks the normal pass and `--reuse`. |
| [`r4119254846`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/55#discussion_r4119254846) — `run_multi_gpu.sh` builds a relative merge destination and then copies from inside each worker directory, so copies fail while `find` exits zero, and the following `--only_do_unfinished` pass reprocesses the whole dataset and presents it as a merge | **Superseded, and the class is now tested.** `run_multi_gpu.sh` does not exist here; `merge_workers.py` never chdirs and resolves `--out`. The guarantee that matters is that the aggregate step cannot run once staging has failed, so `case_failed_staging_never_reprocesses` asserts the binary is not invoked at all, and `case_merge_out_is_resolved` runs the merge from a different cwd with a relative `--out`. |
| [`r4119476076`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/106#discussion_r4119476076) — report identity still not injective: `a/b` and `a__b` share a filename, so `--reuse` can turn a fail-then-pass pair into a false 2/2 PASS | **Fixed.** The identifier is a sha256 digest of the exact root; the readable label carries no identity. Each report also gets an origin sidecar pinning the root, both trees, the comparator and every input file's size and mtime, and `--reuse` refuses a missing, unreadable or mismatched one. |
| [`r4119476085`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/106#discussion_r4119476085) — collision/decoration preflight ran on raw roots, so `/a/x.tif` and `a/x.tif` both reach `a/x.*` and one surviving pair satisfies two movies | **Fixed.** Preflight canonicalizes exactly as the runner and merger do, the manifest publishes canonical roots, and the merge and comparator independently refuse a manifest whose roots collide after normalization. |
| [`r4119254855`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/55#discussion_r4119254855) — undeclared `bc` dependency aborts every otherwise successful run under `set -e` | **Superseded.** The shell launcher is replaced by `run_multi_gpu.py`, which measures elapsed time with `time.time()`. No tool shipped here shells out to `bc`. |

**PR55's own limitations, unchanged by this PR.** Its four files remain on the
obsolete `feat/issue-50-cuda-end-to-end-residency` lineage; its `--merge-star`
path produces a degraded `logfile.pdf` by its own admission; and the four-GPU
SCARF figures associated with it are on source `0c7d68f` with their timed output
arrays deleted, so they are not a current-main scaling curve and no arm of them
can be certified by a separate parity run. Nothing in this PR revives, imports
or re-owns that branch.
