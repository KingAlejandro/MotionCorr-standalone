# CPU dataset throughput experiment, 14 October 2026

Refs #10 and #26. No production source or defaults change. A guarded Linux CTest registers the nine light diagnostic-tool controls (30-second timeout); missing cgroup-v2 accounting, pidfd support or two allocated CPU IDs is an explicit skip. Base main
`116eb04ad359cd5bf789b28809fc2047ea155b9b`; #178 is a separately identified
memory treatment, not assumed to improve individual-movie speed.

**Measurement venue update:** Alex has reauthorized explicitly labelled container
diagnostic timing. Those runs remain queued behind the other three experiments;
no local movie or dataset payload has been launched for this experiment yet.
The primary bounded series uses #178 only at 1x4, 2x2 and 4x1; main versus #178
full-24-frame budget refusals remain separate. The 12-selected-frame tutorial
series is separate again and runs only if its calibrated live memory preflight
permits it. No local result will be pooled with cpu64.

The unrun [cpu64-native protocol](cpu64-native-protocol.md) requires the observed
hostname, coordinated occupancy/NUMA/RAM allocation and confirmed shared lock,
then uses the existing production dataset coordinator. Native access is
currently unavailable. The 8 GiB refusals below are container-only and establish
no VM capacity limit.

## Earlier work

This is not a new idea. The [#26 audit](https://github.com/KingAlejandro/MotionCorr-standalone/issues/26#issuecomment-5825337317)
already measured 24 tutorial movies on cpu64 at the older `3e3a196` source with
a fixed 16-CPU budget: 1x16, 2x8, 4x4 and 8x2 process/thread layouts. The
reported dataset walls were 121.8, 91.5, 84.2 and 86.0 seconds. These numbers
are historical evidence, not a current-main or local-host baseline. That audit
also recorded a 4x4 slowdown to 255 seconds when all processes bound themselves
to the same OpenMP place list. Each worker must receive a disjoint CPU mask.

[PR109](https://github.com/KingAlejandro/MotionCorr-standalone/pull/109) repeated
the single-process thread/binding study on a later base, retaining substantial
CPU interference limitations; its fixed-budget worker phase remained protocol
only. [PR121](https://github.com/KingAlejandro/MotionCorr-standalone/pull/121)
is a persistent TIFF reader-pool no-go, rather than evidence for CPU movie-process
scaling. Existing #53 worker/shard/merge machinery supports CPU workers and full
canonical dataset publication, so a competing production scheduler is unnecessary.

## Questions and matched endpoints

1. At exactly four allocated CPU IDs, how does 1x4 compare with 2x2 and 4x1?
2. Does #178 permit a layout that main cannot fit under the same RAM budget?
3. Do requested per-movie products and the final canonical joint STAR remain
   bit-identical when movies execute in separate processes?

The four synthetic entries are hardlinks of one 512x512x16 input, and the two
tutorial entries are hardlinks of one 3710x3838x24 TIFF. Unique paths give each
entry independent movie products, but the encoded bytes and underlying inode
are shared. This measures scheduling and repeated-workload/page-cache behavior,
not heterogeneity or stragglers across independent experimental movies. A native
representative dataset remains necessary.

Each series fixes the binary revision, immutable input STAR/movie/gain hashes,
product options, seed, aggregate CPU IDs and memory budget. A process invokes
ordinary sequential movie processing; seed 1 is reset by the runner per movie.
No concurrent movies are introduced into one process with its global RNG.

The timed endpoint includes STAR partitioning, all workers, checked staging and
one full `--aggregate_only` dataset STAR/PDF publication. Worker joint PDFs are
suppressed with the existing `--skip_report_pdf`, identically for every layout.
Postpublication identity verification is outside timing. Separate worker-phase
wall times are diagnostic, not substitutes for dataset readiness. Replicates
alternate forward/reverse configuration order; one warmup per configuration is
excluded. Retain every run, including failures and preflight skips. Use six
measured replicates before quoting the profiling kit's nonparametric median
interval; small-host effects do not transfer to cpu64 or SCARF.

## Host and resource limits

The local container reports one NUMA node, Xeon Platinum 8573C, nine visible CPU
IDs, an eight-CPU cgroup quota and an 8 GiB cgroup memory limit. Its mounted
`/proc` disagrees with the PID namespace of launched children. The production
`tools/multi_gpu/run_dataset.py` ownership gate must remain fail-closed; its
failure is retained as `inherited-main-local-ctest.log` from the prior fresh unchanged-main build, with source and environment documented in #179; a new native throughput PASS is not inferred from it. No local result certifies physical-host
isolation, descendant containment or NUMA placement. Native cpu64/SCARF runs
must use that production harness and record actual memory policy/residency.

The diagnostic tool `tools/multi_gpu/cpu_throughput_experiment.py` reuses the
existing STAR partitioner, output-path attribution, staging, canonical joint
STAR row-order and strict full-output identity helpers. Each direct child sets
and reads its affinity before exec, and `wait4` records its actual exit/rusage.
Only directly owned unreaped children or their kernel pidfds may be signaled;
no process-name scans or unrelated groups are touched. Production worker status
is never fabricated or weakened. Every diagnostic record has `certified:false`.

All configurations cover the same CPU IDs with disjoint worker masks, set
`OMP_DYNAMIC=FALSE`, `OMP_PROC_BIND=close`, `OMP_PLACES=cores`, passive waiting,
and one thread in unrelated numerical libraries. Each worker's `--j` and
`OMP_NUM_THREADS` equal its mask width. Child self-affinity is witnessed before
exec, not assumed from a taskset string; changes after exec are unobserved.
Holding binding/waiting fixed here does not establish either as a default.

Before every launch, memory preflight requires the current cgroup charge plus
calibrated per-worker peak RSS times the worker count plus at least 1 GiB
headroom to fit the explicit budget and cgroup limit. This is conservative and
does not assume cache reclamation. A rejected layout is SKIP, not a timed failure
or OOM. Sum of individual worker high-water RSS values is recorded explicitly
as such; it is not simultaneous aggregate tree RSS. The standard native harness
can provide the latter when its process view is valid.

The 24-frame tutorial's main peak (~4.39 GiB) excludes two workers under an
8 GiB budget even before headroom. #178 (~3.13 GiB) also currently fails the
conservative two-worker preflight once the current cgroup charge and headroom
are included. Do not force it. A separately labelled 12-selected-frame series
can test a real-size working set if measured calibration permits it. Small
512x512 inputs permit the 4x1 control without making a realistic full-size
capacity claim.

## Running

The tool takes a JSON plan with `star`, `worker_args`, `required_products`,
`cpu_budget`, `memory_budget_bytes`, `headroom_bytes`, `seed`, `warmups`,
`replicates`, and `configurations`. Each configuration contains a unique `name`,
an absolute `binary`, calibrated `worker_rss_kib`, and `masks` such as `["0-3"]`,
`["0-1","2-3"]`, or `["0","1","2","3"]`.

```sh
python3 tools/multi_gpu/cpu_throughput_experiment.py \
  --plan plan.json --out fresh-preflight
python3 tools/multi_gpu/cpu_throughput_experiment.py \
  --plan plan.json --out fresh-results --execute-diagnostic
python3 tools/multi_gpu/test_cpu_throughput_experiment.py
```

The global `/tmp/motioncorr-bench.lock` is acquired nonblocking before payloads.
The task coordinator must also finish all local builds/tests before timing;
this fallback cannot certify external host quiescence. Nonzero worker exits,
unassigned/misrouted/missing products, changed input/binary, aggregate product
rewrites/additions, incomplete PDFs, noncanonical STAR rows or unequal complete
output trees stop the experiment. No new numerical tolerances are introduced.

## Results

Pending execution. Small JSON plans and the exact planned STAR rows are retained
under `planned/`; their absolute paths describe this scratch venue. Recreate the
hardlinks from the matching SHA256 input files and substitute absolute binary,
STAR and gain paths for another venue. The 12-frame `worker_rss_kib` values are
provisional and must be replaced by measured calibration before a two-worker
launch. The one-worker calibration conservatively uses #178's already measured
full-24-frame peak. `tutorial24-budget-plan.json` and its preflight are separate
from the 12-frame experiment. No planned configuration is a run or a pass.

Nine light controls currently pass: disjoint budget and
reserved-argument refusals, memory refusal, checked staging and missing-output
negative, misrouting negative, unassigned-output negative, direct child
self-affinity and nonzero-exit negative, same-byte aggregate rewrite negative, immutable-input mutation negative, and injected second-launch failure with first-child reaping. No speed, RAM-capacity, NUMA or
whole-dataset identity result is claimed before measurement.
