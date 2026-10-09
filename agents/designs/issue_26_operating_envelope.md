# Issue 26: current-main CPU/CUDA operating-envelope measurement contract

This is the measurement ADR for the one shared operating-envelope study named in
[#66's execution plan](https://github.com/KingAlejandro/MotionCorr-standalone/issues/66#issuecomment-5860352766)
section B. It defines what is measured, what each number is allowed to claim, and where the
study stops. It authorises no production source change: the whitelist below is documentation,
a runner and evidence only.

## 1. Why the existing numbers cannot be reused

Three separate bodies of timing evidence exist and none of them describes current main.

The issue body's $j=1..4$ table comes from `4-gpu-vm` before the shared-host CPU cap existed,
so its host-side stages assumed all 124 logical CPUs. The 2026-09-25 audit in this issue's
first comment is sound work but pins source `3e3a1967`, which predates #82, #90 and #91 —
the merged TIFF, gain-cache and damaged-movie changes land directly on the stages it
measured. PR55's four-GPU SCARF figures lost their timed output arrays. Per the round
contract a historical timing is never relabelled current after a rebase, so all three are
prior art to be re-checked, not a baseline to extend.

Current main is pinned here at `4c952b3f54479653512c4d208e09c9a8c02f3726`.

## 2. What a timed arm must carry to count

A wall-clock number with no witness of what produced it is not evidence. Every timed arm
retains, in its own record:

- **Identity.** Source tree digest, binary `sha256`, `CMAKE_BUILD_TYPE` and the literal
  `flags.make`, compiler/CUDA/FFTW/libtiff versions, movie and gain `sha256`.
  `CMakeLists.txt` defaults `CMAKE_BUILD_TYPE` to empty, so an unqualified configure builds
  `-O0` and inflates every host-side stage; the recorded build type is what makes the arm
  comparable, not an assumption.
- **Placement.** The requested CPU list, the *actually inherited* `Cpus_allowed_list` and
  `Mems_allowed_list`, the `lscpu -p=CPU,NODE,SOCKET,CORE` mapping for that list, and
  per-node residency. A mask is an admission lane, not a locality claim.

  **The memory witness must follow the payload, identified by `/proc/<pid>/exe`, with its
  pid, session and start time recorded.** The runner spawns
  `taskset … /usr/bin/time -v <binary>`, so the pid it holds is the launcher and `taskset`
  execs into `/usr/bin/time`, not into the payload. Sampling the launcher produced a
  published claim about `/usr/bin/time`'s few megabytes. Residency is aggregated from
  `numa_maps` page counts times each mapping's own `kernelpagesize_kB`, in **bytes**:
  `numastat -p` reports MB, and its "Total 1.45" was read as 1.45 GB. Cpuset inheritance,
  process-tree RSS and per-node residency are three different witnesses and are never
  merged.
- **Device.** GPU UUID and the visible ordinal it was addressed by, plus a per-movie witness
  from the run log that a CUDA path actually executed. Device index alone is not identity.
- **Intervals.** Process wall and CPU (user+sys) from `/usr/bin/time -v`, plus the binary's
  own `TIMING` stage intervals from the separately built profiled binary. Stage intervals
  nest and overlap, so they are reported as a labelled tree and never summed into a total.
- **Memory.** Simultaneously sampled process-tree RSS, and device memory from an explicitly
  labelled NVML sampler. A sampled peak is a lower bound on the true peak and is never
  reported as an allocator-traced peak. **The CUDA profile's `Peak GPU memory allocated` is
  neither**: it is per-call buffer-size accounting (`cuda_alignpatch.cu:310-318`), emitted
  once per global/local call, so no statistic over it is a process high-water mark and its
  sum across calls has no physical meaning. Repeated instrumented keys are never collapsed
  by addition; each keeps its occurrences with explicit `n`/`max`, and size-like tags
  withhold `sum` outright. A real per-process device high-water mark requires live
  allocation accounting or an allocator trace, and this study has neither.
- **Interference.** 1 Hz sampling of non-own CPU usage for the whole run, reported as
  mean/max/n, not a probe before and after.
- **Products.** The complete output set, compared against the same-backend baseline as
  ordered pixels, core header, and MRC labels with only RELION's clock stamp masked — the
  same decomposition `docs/gate_contract.md` publishes as `--gate exact`. Text products are
  compared after substituting the run's own absolute output path, which MotionCorr embeds in
  the EPS plot title, `corrected_micrographs.star` and the `.pdf.lst` lists; PDFs are checked
  for presence and size only, because ghostscript stamps a creation date. An arm that lost or
  failed a movie is not a faster arm, and an output that cannot be parsed is reported as
  unparseable rather than as a pixel mismatch.

Two exclusions are load-bearing. TIFF cost is never derived as wall minus GPU kernel timers,
because those timers do not cover the whole run. And profiled and unprofiled binaries are
separate classes of arm that are never mixed inside one comparison.

## 3. Statistical design

Process wall noise on `4-gpu-vm` is about 4%. An unpaired $n=6$ series has 64 possible sign
outcomes and therefore cannot reach the 1% level before any data is collected; two tasks
published wrong conclusions from exactly that design, including a null a larger run reversed
in sign.

All A/B comparison is therefore paired with the arm order alternating inside each pair and
the order label retained, which recovers the positional bias $P$ — the advantage to whichever
arm runs second, mostly input page-cache warming — from `observed = E ± P` at no extra cost.
$P$ is a property of the workload, not the host, and has been measured at 2.5 ms for
GPU-side arithmetic and about 20 ms for a TIFF/MRC change on this machine, so it is never
assumed negligible.

Screening uses three pairs per configuration on a declared subset. Finalists get five
confirmation pairs on all 24 movies. Where the resulting uncertainty overlaps the effect
being claimed, the report says so rather than extending until a threshold is crossed.

Configurations whose *effective* settings collide — an I/O cap above $j$, for example — are
recorded as one treatment, not timed twice as if distinct.

## 4. Phases

**Phase 0, frozen baseline.** Release CUDA and Release CUDA+`TIMING` builds from the pinned
tree; a serial one-GPU run over all 24 tutorial movies; startup, per-movie and final
reporting intervals recorded separately; full product comparison against the same-backend
baseline.

**Phase 1, thread and I/O screen.** One GPU, $j \in \{1,2,4,8\}$ and effective I/O cap in
$\{1,2,4,8\}$ where it does not exceed $j$. Requested and effective counts are both recorded.
Screen on the declared subset, confirm finalists on all 24.

**Phase 2, fixed-budget workers.** The protocol is prepared here and is deliberately not
executed against a scheduler written by this task: #53/PR55 owns executable workers. Under a
fixed aggregate CPU budget the initial hypotheses are one worker at $j$8, two at $j$4 and four
at $j$2, whole process tree pinned inside the allowed cpuset. These are hypotheses, not
measured optima. A scaled-resource series, where host CPU count grows with GPU count, is a
separate series and is never merged into the fixed-budget curve. VM 80 GB and SCARF 40 GB
device results are likewise never joined into one speedup curve.

**Phase 3** — workload shape, frame counts, geometry, heterogeneous costs — is out of scope
for this round and is listed as an explicit unrun case.

## 5. Host policy actually in force

`4-gpu-vm` work runs under a top-level `taskset -c 96-111` (16 logical CPUs, all NUMA node 1
on this guest), build parallelism 8, one timed benchmark at a time behind
`flock /tmp/motioncorr-bench.lock`, at most two idle GPUs. The flock is the only occupancy
test; `/tmp/motioncorr-gpu-timing.lock` is a decoration that has twice asserted a holder that
no longer existed. The flock serialises ownership but not the previous holder's load decay
tail, so a settle gate — `load1` below threshold and no `cc1plus`/`nvcc`/`cicc`/`ptxas` by
exact name — runs *after* acquisition, with the observed wait logged.

`cpu64` lanes and locks, in full: this issue's measured runs use `taskset -c 0-31` (exactly
NUMA node 0) behind `flock /tmp/motioncorr-issue96-cpu-measure.lock`; other workers' heavy
work uses `32-63` behind `/tmp/motioncorr-issue96-cpu-validation.lock`; a whole-host 64-core
run requires **both** locks. `ctffind` is never altered. Two foreign `ctffind` processes run there
permanently at ~100% each and are **unpinned** (`Cpus_allowed_list: 0-63`), so they can and do
enter the measurement lane. They are not altered and not waited out; they are sampled per run
and reported as interference.

**Cancellation must stop the owned tree, and a failed gate must not pass as clean.** The
payload runs in its own session so the whole group can be terminated and joined; signalling
the launcher pid alone leaves MotionCorr or its ghostscript child running, burning the cpuset
and the GPU into the next arm — possibly someone else's, after the lock is released. Because
the payload then has its own session, the interference sampler must **adopt** it, or it will
report the process under measurement as foreign load in its own lane. An arm whose settle
gate timed out, or that started with foreign threads in the lane, is recorded as
**quarantined**: kept in the record, excluded from clean-evidence claims.

**Ownership must be an identity the runner actually owns.** Treating "the runner's session"
as own is sound only if that session contains nothing else. The reproduction command starts
plain `python3` under `taskset`/`flock` with no `setsid`, so the sid is the launching
shell's, and anything else started from that shell would be silently excluded from every
interference figure — real lane contention reported as zero. The runner now establishes an
isolated session at startup, or records that it could not and falls back to subtree
ownership, which cannot hide a same-shell stranger. The basis is written into every record.

**Process-tree RSS means the whole tree.** `ps --ppid` selects only immediate children, so
helpers spawned one level deeper are omitted from a figure that claims to be a tree total.
The sampler walks all owned descendants per sample and records the peak's composition and
unit alongside its value.

**The timing population is not the audit population.** Failed, timed-out, quarantined,
cleanup-unconfirmed and product-less runs stay in the product audit — deleting a failed
record is worse than keeping it — but never enter a median or a paired difference. A run
that died early has a short wall time, and admitting it would make the configuration that
failed look fastest, inverting the contract's own rule that a failed movie is not a faster
arm.

**A control that re-implements the logic it verifies is not a control.** Twice in this
issue a check loaded the module under test and then reproduced its predicate inline, so
reverting the production code left the check green — first the payload-versus-launcher
control, then the timing-exclusion and reference-keying controls. Every control must invoke
the production entry point and assert on what it emits, and must be mutation-tested by
reverting the fix and observing the failure.

**A same-backend baseline must be keyed by backend.** Reference arms are keyed on input set
**and** backend/build class, and two references colliding on that key are rejected rather
than silently overwriting one another; otherwise a combined CPU/CUDA series scores every arm
against whichever reference was registered last. The build class must survive a missing
binary hash: a plan may declare the binary relative to the arm's cwd, and keying on the bare
basename would collapse a Release and a Release+`TIMING` build in sibling directories into
one class — which the product comparison cannot catch, because `TIMING` output goes to
stdout rather than into a product.

**Interference evidence must be retained at per-sample and PID level.** The 2026-09-27
`cpu64` series retained only per-arm aggregates — a max over samples, and per-command
*accumulated* thread-sample hits — which is enough to show that foreign work entered the
lane but not enough to say how many threads any one command ran simultaneously, nor to
attribute the work to anything. Any re-measurement must keep the per-sample series and the
PID, session id and command line of foreign processes, or it will again be able to observe
contamination without being able to characterise or attribute it.

Interference is identified by process subtree, not by username. Every concurrent round worker
on `cpu64` runs as `ubuntu`, and so do both `ctffind` jobs, so a user-based filter reports zero
foreign load there regardless of what is actually running — a check that structurally cannot
observe what it asserts.

For the same reason the settle gate has two modes. Waiting for global `load1` is right when
the mutex confers exclusive use of the machine, as on `4-gpu-vm`. On `cpu64`, where other
workers hold a different lock in a disjoint lane, the gate instead waits for *this run's own
cpuset* to be free of busy foreign threads and records `load1` as a witness. Because `ctffind`
is unpinned and permanent, that gate is expected to time out at the start of a `cpu64` series;
the timeout is logged, and it is the evidence that a clean lane is not obtainable on that host
rather than a defect in the gate.

## 6. Whitelist

Documentation, measurement tooling and evidence only. No file under `src/` is modified by
this issue.

| Path | Kind |
| :-- | :-- |
| `agents/designs/issue_26_operating_envelope.md` | this ADR |
| `WORKER_STATUS.md` | round handoff status |
| `tools/envelope_runner.py` | measurement runner |
| `tools/envelope_report.py` | series analyser and product-equality verdict |
| `tools/test_envelope_report.py` | positive and negative controls for that verdict |
| `tools/test_envelope_interference.py` | controls for the interference witness (Linux only) |
| `tools/test_envelope_runner.py` | negative controls: sequential sizes are not a peak, the witness follows the payload not the launcher, cancellation reaps a child that outlives its parent, the payload is not its own interference |
| `docs/operating_envelope_issue26.md` | report and operating guide |
| `docs/benchmark_logs/issue26_envelope_*/**` | raw per-run records |

## 7. Stop criteria

The round stops at a bounded first-stage result: a frozen Release one-GPU baseline, a
screened $j$/IO recommendation with its confirmation pairs, a prepared fixed-budget worker
protocol, and an operating guide that states its own limits. A negative or null scaling
result is reported as such. Expansion beyond this needs separate justification.
