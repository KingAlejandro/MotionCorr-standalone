Bounded #226 D2/D3 normal-merge integration, 2026-10-22

Branch: `integration/226-d2-d3-20261022`. The clean assigned checkout began at
`1f0a58bf6e0639d8b62f74da52f250cc664c0b30`; a new branch started at D2
`ad0c61a369499b9d1444b804cd9850a167fea646`, without moving another branch.
Normal merge **fe104f217703871c897887a9b7ca3a6bff4b7b69** has parents:

- `ad0c61a369499b9d1444b804cd9850a167fea646` (D2).
- `35d2f950fcb4339e97b9919cdc5b36a4315460ed` (D3 guard and tests).

Normal follow-up merge **6a2e6c1dcdd795cf325c2166bc17c1fcf5eb922b** has parents:

- `fe104f217703871c897887a9b7ca3a6bff4b7b69`.
- `1dbdd47e875422655ad54bd453be01addb2fef5a` (standalone D3 collection repair).

The issue226 discussion, live PR251/252 bodies/reviews/inline comments, CMake,
explicit collection policies and both branches' design/evidence records informed
this integration. `review-context.json` retains the live context; the parent's
later review clearance is attributed in `review-followup.json`. No upstream
full-suite, native, scientific or timing result is transferred to this combination.

CMake and the production runner merged automatically, retaining the D2 admission
and fallback paths and D3 early refusal/fatal-before-plan-release guard. First
merge conflicts were the two `tools/` collection files and one historical
`docs/release/SUPPORT.md` block. Both test lists retain `CudaLocalAdmission`,
`CudaEarlyStreamingOom` and `CudaStreamingPlanClassificationCleanup`, alongside
D1's existing control. The release-note resolution retains the nonempty D2
paragraph and separate D3 addition without revising either historical result.
The classifier test's omission from the D3 required lists was the one collection
finding; this integration fixed it before the parent supplied the standalone
repair. The second merge conflicts were only those same two tool lists; it
retains the union and the standalone explanatory comment and host proof.
No production edit beyond the normal branch combination was made.

Actual build and native source: **fe104f217703871c897887a9b7ca3a6bff4b7b69**.
The follow-up changes collection commentary/docs; `git diff --exit-code fe104f21
6a2e6c1d -- src CMakeLists.txt tests` exits 0. All 266 production/CMake identities
match before and after qualification and after the collection merge; see
`source-equivalence-after-merge.json` and `support/production-source.sha256`.
The complete `git archive` SHA-256 is
`537169afce3f8a0420fe5b0a178335bfc04c467477fe276744448f91fd4c5940`.
All 455 tracked production/build/test/tool inputs are pinned in
`support/build-inputs.sha256`. Actual source/test hashes, generated build-file
hashes, CMake cache, flags and link argv are retained in the raw archive.
The only compiled test overlay is `support/native-receipts.patch`, copied from
D2 support: an extra e10216 geometry and boundary receipts in the native test.
The runner has no production overlay. Native tests are not relabelled as having
compiled the later documentation/collection merge.

Fresh Release CUDA+nvCOMP compilation **PASS**. The selected targets compiled
15:49:55–15:51:56 UTC; both host controls `PatchRetryAdmission`/`PatchRetryState`
**PASS 2/2**, and the focused collection unittest **PASS**. The first full
collection check correctly failed with `BAD_COMMAND` for unrelated registered
executables that the selected-target build had not built. Its exit 1 and JSON
are retained. Building the remaining targets with unchanged source/flags completed
15:53:01–15:56:42 UTC; no native process had yet run. The resulting 115-test
collection and required-name validator **PASS**. Removing each of the three
CUDA controls, replacing it with filler at unchanged count 115, exits 1 with the
specific missing-name diagnostic. This is a collection result, not 115 tests run.
The later normal merge was checked locally with the specified Python: focused
unittest **PASS**; actual 115-test collection **PASS**; all three omissions
**rejected**. See `collection-after-d3-merge.log` and `collection-after-merge.json`.
The local CTest collection copy strips trailing spaces only; unchanged raw CTest
bytes remain in the archive and parsed-data identity was verified. The standalone
old-accept/new-reject proof remains unchanged in the D3 directory.

The one combined-source native phase ran 15:57:52–15:58:35 UTC, exit 0:

- `CudaLocalAdmission` **PASS**: initial local-stage boundary 6,135,264 bytes,
  28 independent retry boundaries across four geometries, plus invalid/overflow
  checks. For e10216, S = 158,299,360; fresh non-cuFFT buffers = 22,407,056;
  actual cuFFT work = 11,112,768; complete requirement = **191,819,184 bytes**.
  The literal **175,000,000** interval declines; required-minus-one declines,
  exact required admits. Real cuFFT planning is used with only free bytes wrapped.
- `CudaEarlyStreamingOom` **PASS**: early named required/available refusal,
  no failed-movie or joint product, healthy next-movie products identical to its
  separately launched reference.
- `CudaStreamingPlanClassificationCleanup` **PASS 16/16**, including its own
  reference: healthy streaming; create/auto/make allocation and nonallocation
  errors; cleanup errors; earlier fatal state versus later success/OOM; earlier
  nonallocation error versus cleanup OOM; and earlier OOM versus cleanup fatal.
  Each ordinary failing job exits 1, preserves only the healthy next movie's
  strict products, and withholds joint output. Healthy streaming exits 0 and
  publishes both movies and joint output. Handle/allocator witnesses balance.
  Fatal statuses here are simulated returns around healthy native GPU work,
  not genuine illegal-access or poisoned-device qualification.

Only after fresh RAM/scratch/input checks, the fixed e10216 runner phase ran
15:59:30–16:00:47 UTC, exit 0. Available RAM was 450,589,986,816 bytes; scratch
532,913,426,432 bytes. The input is the original first 4096×4096×59 signed-int16
MRC, 1,979,712,512 bytes, SHA-256
`f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56`, checked before
and after. Original/adapted QM harness, corpus metadata, unchanged comparator,
existing balloon executable/source and actual runner hashes are pinned in
`integration.json`. Harness changes are only new scratch/build paths, CPUs,
UUID and `--j 1`; `support/qm-resources.patch` records them. Existing D2 support
was read and copied, never modified in its original directory/worktree.

Each case was launched once with fresh outputs. All four exit 0 and publish the
movie MRC/STAR and joint STAR. All three constrained strict MRC/STAR comparisons
**PASS** with the unchanged comparator and timestamp/output-prefix normalization:

- Reference: 81,154 MiB measured free; compact ingest, resident pipeline, batch
  chunk 4, peak host RSS 2,042 MiB.
- 8 GiB: 8,189 MiB measured free; handled fused gain/sum OOM, CPU preprocessing
  and streaming fallback; peak RSS 7,880 MiB.
- 8.5 GiB: 8,701 MiB measured free; resident preprocessing, chunk 0; retry
  declines at 78,839,808 available versus 191,819,184 required and completes via
  streaming; peak RSS 8,000 MiB. This headroom is below S and does not independently
  discriminate the old S-only bound; the native boundary test does.
- 8.75 GiB: 8,957 MiB measured free; resident pipeline, chunk 0; peak RSS 2,042 MiB.

No named composition refusal or unexpected runner failure occurred. Separate
whole-tree comparisons honestly retain **FAIL/exit 1, 3/3**, differing only in
per-movie route/memory logs. No comparison threshold or numerical predicate was
relaxed. Each product comparison checks the full 16,777,216-pixel MRC header,
extended header/payload and the movie/joint STAR products. Time and RSS are
provenance during parallel activity; no performance comparison is made.

Venue: `ssh -J ccp4-gateway 4GPUs`, verified hostname `4-gpu-vm`; new scratch
`/mnt/clathrin/alex-226-d2-d3-integration-20261022T154900Z`. Only physical GPU3,
UUID `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, was used. CPUs10–13, compile
parallelism 2, runtime `--j 1` and OMP/OpenBLAS/MKL/NumExpr thread caps 1 are
inherited by children. GCC13.3.0, CUDA12.8.61, CMake3.28.3, existing nvCOMP5.3.0.16
at `/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive`, remote
`/home/alex/.mc-venv/bin/python3` with NumPy2.5.3. Local host receipt checks use
`/Users/alex.konstantinov/.local/bin/python3`.

Common build and canonical GPU3 correctness locks were nonblocking. GPU3 was held
through each native/runner phase and its post-health. Benchmark probes were
released before occupancy rechecks and repeated before native work. Every one
of **266** retained health samples checks UUID, recovery action, all numeric
ECC/retired-page counters, remapping and foreign GPU occupancy. Predefined
post-utilization settling was at most twenty one-second samples, permitted only
with healthy status, no apps and normal memory; no health waiver was applied.
All actual MotionCorr invocations were counted: **23** (19 D3 controls including
references plus four e10216 runs), separately one native-admission executable,
two host retry executables and three balloons. No native rerun occurred. All
three balloons were identity-checked and reaped with exit -15. No foreign PID
was signalled. Detached driver PIDs/exits were reconciled before the next phase.

At final collection, 16:01:58 UTC, GPU3 was healthy, 1 MiB used, 0% utilization,
no apps, no recovery action; GPU3/build/benchmark lock probes all exit 0. Scratch
and exact source/binaries remain remotely for review. The protected root stays
at `c8844894` with its untracked `pr117-fix-measure-20260929/`, and the starting
ref remains at `1f0a58bf`. HEAD reflog records its rename from `t3/1544d45f` to
`226-d2-d3-20261022` before this agent checkout; the renamed ref is preserved.
Exact observations are in `protected-checkouts.json`. No independent checkout,
work or service was modified.

`raw-logs.tgz` contains **647** indexed files (695,240 compressed bytes): phase
PIDs/exits, exact argv, build/collection logs including the preparation failure,
binary/input/test/source identities, D3 receipts/inventories, all health XML,
product comparisons and cleanup/release records. `raw-index.json` hashes every
member; `archive.sha256` binds the archive. Executables, source archive and
MRC/MRCS/PDF payloads are excluded from staging. `integration.json` is the compact
receipt. Read-only local verification, including every archive member, all 266
health XML samples, six unchanged binary hashes and the retained gates, **PASS**:

```
/Users/alex.konstantinov/.local/bin/python3 \
  docs/rc0/issue226/integration_20261022/support/verify.py
```

Exact reproducible commands are in `support/build.sh`, `complete_build.sh`,
`native.py`, `products.py`, and the raw command/process receipts. Drivers were
launched with `nohup`, the explicit thread caps above and `taskset -c 10-13`;
Python drivers use `/home/alex/.mc-venv/bin/python3 -I`. Scripts intentionally
refuse to reuse this campaign's existing outputs.

**UNRUN:** full CPU/CUDA/nvCOMP suites, 10441/Falcon/QF, scientific pilots,
performance qualification, real smaller cards, host exhaustion, genuine poisoned
contexts and kernel Xid inspection. Compilation and these bounded controls do
not imply those claims. No gates, tolerances, defaults, memory policy, dependencies
or upstream notices were changed beyond the explicitly combined source packages.
No push, main merge, GitHub comment, Notion write or new PR was performed here;
independent integration review and publication remain with the parent.
