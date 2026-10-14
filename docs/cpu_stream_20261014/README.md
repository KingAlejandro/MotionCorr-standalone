# CPU reconstruction lifetime experiment, 14 October 2026

Refs #10; independent of draft PR #177. See [design.md](design.md) for ownership
and numerical boundaries and [opportunities.md](opportunities.md) for the
lessons from #177 and ranked follow-ups.

## Source and measurement identity

Reference is unchanged main `116eb04ad359cd5bf789b28809fc2047ea155b9b`.
Candidate production/test code is published as
`5a6812baf69979a8446baae2835188a85336acf3`. The local measurement commit
`c9dbe5957898f5206cb05ea5daaa62ae3358218a` has the identical complete tree
`64057a81711dd137dccecbc08536a0eedbff7192`; the API commit uses the authenticated
KingAlejandro author/committer. Subsequent commits add evidence only.

Release CPU-only builds use GCC 13.3, CMake 3.28.3, FFTW 3.3.10,
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`, without fast-math. The reference binary
SHA256 is `b9f8912d65c79b572f2764628a914edaea3fe46380af0f98574ec0b087231674`;
candidate is `0160ab12cb348d8dbab5763f12449e8920986bb70d34b94d42e9e4675ba230de`.
Configure/build logs, library paths and CPU/cgroup details are retained here.
Exact commands, binary/source pins and input SHA256 values accompany each
measurement JSON. The measured production source did not change during runs.

The host reports Intel Xeon Platinum 8573C, with eight CPUs of cgroup quota
and an 8 GiB memory limit. Tutorial runs use a four-CPU mask `0-3` and j4;
synthetic runs use mask `0`/j1 or `0-3`/j4. Both arms have matching OpenMP
placement/dynamic settings and one OpenBLAS thread. There is no concurrent
local build, validation suite or other benchmark. Diagnostic profiles take
the same shared lock and run separately.

The mounted `/proc` uses a different PID namespace from children. The standard
kit's per-PID ownership/affinity cannot be certified here. The separate
`run_unprofiled.py` checks affinity from inside a taskset child, locks the lane,
rejects active compilers, warms each arm once, alternates AB/BA and records
spawn-to-reap monotonic wall time and `wait4` CPU/peak RSS. It runs the existing
strict full-tree product comparator after every pair. This is a bounded
fallback observation, **not a clean mcprof verdict or certified physical-host
isolation**. Timings from different hosts and earlier sessions are not pooled.

## Correctness and CI

- `CpuUnweightedStream` passes its bitwise products, parity, immutable alias,
  progress, temporal-index and allocation-lifetime witnesses. On GNU/ELF it
  measures N live corrected images in the former sequence and exactly one in
  the candidate, independent of frame count, with no surviving scratch.
  Negative witnesses show that removing the float store or resetting model
  time to zero changes the fixtures.
- Local full CTest: candidate **51/53**, reference **50/52**. Both fail exactly
  `ProfilingKit` and `MultiGpuScheduling` on process ownership/PID identity.
  Logs preserve those failures; neither test is disabled or relaxed.
- [GitHub Linux CI run 508](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38636266198)
  is **green on `5a6812b`**: Ubuntu **53/53 CTests**, known-motion aggregate,
  canonical fixture preflight/digests, smoke products and failure controls.
  CUDA and linked controls compile successfully. There is **no native GPU
  execution or GPU performance evidence**. `ci-status.json` and the full
  Ubuntu job log retain this separate native-host outcome.
- Known-motion aggregate **PASS** across every default case, including j1,
  j4 and j1 dose/noDW variants. The existing `km_local_noisy` characterization
  accuracy remains **FAIL**; it is not hidden by the aggregate. All execution,
  backend, invariance and applied-image checks pass. Twelve full output-tree
  comparisons against reference pass, including **16 MRC and 24 STAR file
  pairs**, after the existing writer-clock/root normalization. No numeric
  tolerance was loosened.

## Unprofiled results

One warmup per arm, followed by six measured pairs in each of five configurations:
**70 unprofiled runs**, 30 measured pairs and five warmup pairs. All **35 full
output-tree comparisons pass**. Alongside known-motion and the diagnostic pair,
**214 MRC/STAR file pairs** match exactly under the existing normalization;
`canonical-product-hashes.json` retains their normalized SHA256 values.

Tutorial, 3710 x 3838 x 24, 5x5, j4, dose + noDW + even/odd:

- Maximum observed process RSS: **4,600,912 / 3,286,696 KiB**, or
  **4.388 / 3.134 GiB** (reference/candidate). Median peaks are
  **4,600,778 / 3,265,750 KiB**, or **4.388 / 3.114 GiB**.
  Every measured pair reduces peak RSS by **28.56-29.02%**.
- Wall medians: **54.196 / 51.480 s**. Paired candidate-minus-reference
  differences: **+0.869, -2.811, -6.976, -13.533, -7.695, +8.819 s**.
  The paired median is -4.894 s; its distribution-free 96.875% interval is
  **[-13.533, +8.819] s**, including zero. Pair scatter is 6.349 s.
  **No resolved speed improvement or slowdown.** Do not turn the lower
  candidate median into a speedup percentage.
- CPU medians: **166.644 / 161.636 s**. This does not overcome the wall-time
  uncertainty or certify host isolation.

Synthetic, 512 x 512 x 16, six pairs each; wall medians (reference/candidate):

- Global, no dose, j1: **0.638 / 1.197 s**.
- Global, no dose, j4: **0.756 / 0.634 s**.
- 5x5, dose + noDW + even/odd, j1: **1.681 / 1.774 s**.
- 5x5, dose + noDW + even/odd, j4: **1.140 / 1.092 s**.

Every synthetic timing interval includes zero, including the j1 global case
whose candidate median is higher. No timing configuration resolves an effect.
Every synthetic measured pair reduces process peak RSS, by **21.68-26.87%**
across the matrix. See `summary.json` for all raw-pair summaries, ranges,
confidence intervals and order effects. No outlier was removed.

A separate ordinary-binary diagnostic profile per arm also has exact full-tree
identity (`stages/`). Its unweighted stage is **6.160 / 7.456 s**, while several
unchanged stages differ substantially too. Those single profiles do not support
an unweighted-stage speed claim. The reference's full-frame forward, global
inverse and dose inverse FFT intervals total **36.17 s** in a **69.87 s** profiled
process, making full-frame FFT work the clearest next speed investigation.
Do not add nested timers to their parent totals.

`summarize.py` uses the existing paired statistics routines, excludes only the
declared warmups and retains every successful strict pair. Its mathematical
confidence intervals are descriptive for these fallback observations; they do
not repair the uncertified host isolation. Full process peak RSS, rather than
scratch-allocation arithmetic, is the RAM measurement.

The comparator checks complete inventories, MRC header/pixels and normalized
STAR/EPS bytes. Only the existing log timing/PDF-byte exclusions apply. PR #177's
earlier baseline partial temporary-MRC inventory failure remains preserved in
that PR's evidence; it is not removed from or pooled into this population.

## Applicability and remaining work

The saved corrected stack exists only when an unweighted reconstruction is
needed: no dose weighting, `--save_noDW`, or even/odd products. A dose-only run
without these products already skips this stage and should not be promised the
same saving. The scratch lifetime scales from N corrected float frames to one;
the whole-process peak depends on other simultaneously live buffers.

CUDA resident reconstruction does not use this helper. CPU fallback calls do,
so native fallback execution remains additional coverage to obtain on a GPU
host. Keep the PR draft for review and a clean-host representative comparison.
No merge, issue closure or scientific downstream-quality claim is made here.
