# CPU dataset throughput, 14 October 2026

**Outcome:** independent processes improve this small generated workload at a
fixed four-CPU budget. On the real-size, 12-selected-frame tutorial workload,
one measured pair favors two processes, but does not establish a speed gain.
All successful dataset populations preserve complete canonical products exactly.
These are container diagnostics, not a cpu64/SCARF or NUMA recommendation.
No production source, scheduler or defaults change.

## Six-repetition small workload

The same four **distinct generated 512x512x16 float movies** run in every arm,
using #178, 5x5 patches, dose weighting, noDW and even/odd outputs, seed 1.
One warmup per layout is excluded, followed by six forward/reverse interleaved
blocks. All layouts use the same CPU IDs 0-3, partitioned into disjoint masks.

- **1 process x 4 threads:** dataset-ready median **3.352668 s**;
  worker-phase median **2.439343 s**.
- **2 processes x 2 threads:** **2.638860 s**; worker phase **1.735302 s**.
  All six paired dataset deltas favor this layout; median **-0.782467 s**,
  descriptive 96.875% median interval **[-0.969455, -0.153922] s**.
- **4 processes x 1 thread:** **2.526333 s**; worker phase **1.498830 s**.
  All six paired deltas favor this layout; median **-0.888309 s**,
  interval **[-1.200007, -0.713679] s**.

The existing paired routines resolve both multi-process comparisons against
1x4 within this diagnostic series. This is approximately 1.27x/1.33x throughput
from the median dataset times; it does not prove that 4x1 beats 2x2, or predict
large experimental movie performance. Dataset wall includes partition/setup,
workers, checked staging and complete canonical aggregate STAR/PDF publication.
Postpublication identity checks are outside timing. Nothing is omitted from the
measured endpoint. Raw records: [synthetic-six/](synthetic-six/), with
[paired summary](throughput-synthetic-summary.json).

The initial repeated-hardlink synthetic plan was **not timed**. Before timing,
[generate_distinct_inputs.py](generate_distinct_inputs.py) created four new
files without modifying shared inputs or their hardlinks. The fixed source
movie receives a documented float32 scale and deterministic spatial/frame marker.
Both raw file and pixel-payload hashes are distinct. Recipe, NumPy version,
source hash and exact generated hashes are in
[generated-input-manifest.json](generated-input-manifest.json). These are
association/scheduling fixtures, not diversity across experimental acquisitions.

## Separate real-size diagnostic

Two input entries are hardlinks of the same **3710x3838x24 tutorial TIFF**, with
`--last_frame_sum 12`. This is a repeated-input diagnostic with 12 selected
frames; it is not the full-24-frame benchmark or a heterogeneous dataset.
The gain, optics, dose and products match between layouts.

One warmup per layout is excluded, then one measured pair:

- **1x4:** **57.461981 s** for the two-movie complete dataset.
- **2x2:** **50.157370 s**, delta **-7.304611 s**.
- Warmups were **82.640832 / 82.970920 s**, showing substantial variability.

**No resolved speed verdict:** one pair is below the existing six-pair minimum;
no finite resolution or confidence interval is claimed. No sample is dropped,
and these results are not pooled with the small workload or calibration.
All four dataset publications and canonical identities pass, with no skipped
arms. [Raw records](real12-onepair/) and [summary](throughput-tutorial12-summary.json).

## Memory and resource limits

Maximum **sum of individual worker high-water RSS** in the small measured series:
**55,440 / 105,156 / 225,096 KiB** for 1x4 / 2x2 / 4x1. In the real-size series,
including warmups, maxima are **1,903,756 / 3,578,380 KiB** for 1x4 / 2x2.
These sums are not simultaneous aggregate dataset-tree RSS and exclude a
simultaneous accounting of report helpers. They demonstrate the process-memory
tradeoff, not a new memory reduction or a native RAM-capacity result.

Every launch requires current cgroup charge + calibrated worker peaks + at
least 1 GiB headroom to fit the explicit budget and cgroup limit. The 12-frame
bound is the observed **1,934,252 KiB** calibration child peak times 1.10,
rounded to **2,127,678 KiB/worker**. Its calibration observer failed, as retained
below; only the child RSS measurement supplies this conservative bound.

The separate [full-24-frame preflight](tutorial24-budget-preflight.json) refuses
two workers for both main and #178 under this container's 8 GiB budget. Required
charges were about **12.19 / 9.50 GB**, including then-current charge and headroom.
No full-24-frame two-worker payload ran. This is container-only budget evidence;
it establishes no VM limit or demonstrated new full-size capacity from #178.
No cache was reclaimed manually and no unrelated process was touched.

The host reports Xeon Platinum 8573C, nine visible CPU IDs, eight CPUs of quota,
8 GiB RAM limit, one NUMA node and THP `madvise`. Its PID namespace disagrees with
mounted `/proc`. Direct children set/read affinity before exec; `wait4` records
actual exits and rusage. Only directly owned children/kernel handles can be
signaled. Every result has **certified:false**: no physical-host isolation,
descendant-tree containment, post-exec affinity or NUMA-placement certification.
OpenMP binding/places, passive waiting and unrelated numerical-library thread
limits are held fixed, not proposed as new defaults. The shared benchmark lock
and coordinator's exclusive local lane serialize payloads. See
[environment.json](environment.json) and per-child command/affinity records.

## Exactness, retained failures and CI

The successful small series contains **21 complete datasets**. Its **20 nonself
comparisons** cover **320 MRC and 100 STAR pairs**; the measured portion covers
288 MRC and 90 STAR pairs. The real-size series has **four complete datasets**,
**three nonself comparisons**, **24 MRC and nine STAR pairs**; its measured pair
covers 16 MRC and six STAR pairs. Counts exclude each population's self reference
and are retained separately in [comparison-counts.json](comparison-counts.json).
[Canonical SHA256 values](canonical-mrc-star-sha256.json) cover complete normalized
MRC headers/payloads and STAR content. EPS numeric content and list membership/
order also compare exactly. No numerical tolerance is introduced.

Raw products never change. A separate comparison view maps only recorded
worker/merged output-root prefixes and the exact observed report scratch prefix.
The expected report list follows the writer: three all-movie plots at <=3
movies, all/histogram pairs above three. Movie basenames, STAR associations,
plot numbers, membership and order remain intact. Unknown paths fail. Existing
writer-clock/root masks and log/PDF-byte exclusions remain. Ten manual test
methods pass, including copied-view positive and independent 1-ULP pixel,
wrong-movie image, plot-number, list-member and unknown-path negatives. The
actual generated-output wrong-movie negative fails only its replaced MRC after
an unmodified copied-view positive passes.

Retained failures are not counted as pipeline passes or pooled into timing:

- [First cross-layout warmup](failed-warmup/) stopped on worker-root EPS titles
  and random report scratch paths; MRC/STAR products matched. No measured
  repetitions started. The bounded comparison adapter and controls fix this.
- [One-movie calibration](failed-calibration/) had child and aggregate exit 0,
  but its observer incorrectly required six plots. The source emits only three
  because histograms require more than three movies. Overall calibration
  remains **FAIL**; its observed RSS is retained without a performance verdict.
- The initial [copied-tree negative](throughput-association-negative.json)
  retained old text roots and lacked a passing unmodified copy, so it is an
  invalid control. The [corrected control](throughput-association-negative-corrected.json)
  supplies that positive and rejects the replaced image independently.

[CI 517](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38651003895)
passed 52 inherited CTests but omitted the new harness CTest because of a
configure-time cgroup-file guard. Corrected [CI 519](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38652062879) explicitly registered and
passed `CpuDatasetThroughputExperiment` in 0.45 s, **53/53 CTests**, known/canonical/
smoke/failure checks and CUDA compilation on `9a20f17`. Memory controls mock
cgroup snapshots; unavailable pidfd/CPU capabilities skip only affected tests.
Current comparator/small-report code at `c4b826a` passes [CI 524](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38653836536): **53/53
CTests**, the registered harness CTest in **0.42 s**, and its **10 unittest
methods** in **0.183 s**. Known/canonical/smoke/failure checks and CUDA compilation
also pass. No native GPU execution is claimed. Raw CI logs/status and
both old/new manual-control logs are retained without overwriting failures.

## Provenance and native follow-up

Production binary source is #178 `5a6812baf69979a8446baae2835188a85336acf3`,
local identical-tree source `c9dbe5957898f5206cb05ea5daaa62ae3358218a`, binary
SHA256 `0160ab12cb348d8dbab5763f12449e8920986bb70d34b94d42e9e4675ba230de`.
Main base is `116eb04`. Harness source, publication mappings, per-plan tool hashes
and production binary source/hash are distinct in [source-receipt.json](source-receipt.json).
Executed plans inside each population are authoritative; `planned/` archives
unrun initial plans. Raw MRC/EPS/PDF files remain in the recorded scratch paths;
committed evidence retains raw JSON/log/STAR/list files, identities and hashes.

The earlier [#26 audit](https://github.com/KingAlejandro/MotionCorr-standalone/issues/26#issuecomment-5825337317)
already found process-count benefits on older cpu64 source and a large penalty
when several processes bound to the same places. [PR109](https://github.com/KingAlejandro/MotionCorr-standalone/pull/109)
measured later single-process scaling but left its worker phase as protocol.
This is a bounded current-base follow-up, not discovery of a new scheduler.
The existing #53 `run_dataset.py` remains the native publication coordinator.

[cpu64-native-protocol.md](cpu64-native-protocol.md) is **unrun** because access is
unavailable. It requires observed hostname, occupancy, topology, RAM allocation
and the coordinated shared lock before selecting masks. Use a representative
heterogeneous dataset and native process/RSS/NUMA witnesses there; do not pool
these container populations with cpu64 or SCARF. No merge or default change is
recommended from this study.
