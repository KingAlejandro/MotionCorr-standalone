# Issue 69: composed CUDA reliability results

## Latest combined main — 29 September 2026

Current tested source `0f2ddd5d` includes main `6393547e`, the #69 enumeration
recording and preprocessing-disposal fixes, plus PR114's selected-frame recentering.
Native CTest **26/26**, preprocessing **8/8**, enumeration **10/10**, and
retained native recenter off/on witnesses pass. Both GitHub jobs pass at that exact
source. No new performance or full24 claim follows.
[Exact source, commands, outputs, resource identities, limitations and CI](evidence/main-composed-20260929/README.md).

The sections below retain the earlier-source measurements and failures. Their
source hashes and original qualifications still apply.

## Enumeration failure follow-up (29 September)

Source review found two unrecorded `cudaGetDeviceCount` error returns: session
initialization and `cudaPreparePatch`. Commit `7572e3a` records both before returning,
so a fatal returned status remains visible even when the runtime last-error slot is
clean. Recoverable errors and a successful zero-device query retain their old behavior.
The current runner driver is `0e159ff`; its later changes affect only control grading
and provenance. Production/C++ test sources are unchanged from `7572e3a`.

Fresh native results on GPU2 / CPUs112-119: **22/22 CTest**, **301 resource trials plus
six enumeration cases, zero failures**. The production controls located initialization
at query ordinal2 and fallback preparation at ordinal5. Both fatal arms refused further
allocation and published no image/joint STAR. Each of the four recoverable/zero-device
arms produced one MRC/two STAR files exactly matching healthy pixels, full normalized
headers and metadata. Removing either recording line independently fails its matrix
controls and makes that production fatal arm incorrectly complete. Fresh all24 versus
the retained current-main reference matches 24 MRC/25 STAR/**341,735,520 pixels** and
full normalized headers exactly. These are injected statuses, not real context poisoning.

[Commands, source/binary/input hashes, raw logs, mutants and limits](evidence/enumeration-20260929/README.md).
Final independent review and CI for this follow-up remain pending; no merge is implied.

## Initial ownership execution and disposition

Executed production/test source: **078ec5461119b8a51802debc8f2621b3c304a5bc**.
Reference main: **a75a3f87f7ef17e0a29b1c91a1edecda08ebed34**. PR115 contains
that main and preserves the required test inventory, including GlobalIfftElision.
The evidence publication after this source is documentation only.

The known ordinary throwing-path ownership gaps are repaired. PR93 is not imported:
the eight-buffer/eight-event/one-plan scoped baseline derives from PR107, with
additional checked release, immediate invalidation and fixed storage. See
[exact ownership](OWNERSHIP.md). PR93's optional caching must be ported onto this
baseline and independently validated if it is pursued.

**Issue69 is ready for final source review, not closed or merged.** This completes
the bounded implementation and acceptance work described below; it does not certify
every CUDA/driver failure. Earlier review and PR107's 132 trials do not approve this
new ownership implementation. Both GitHub jobs passed at source 078ec54
([run](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/36498471786));
the CUDA CI job is compilation only. No performance inference is made.

## Fresh execution on the composed source

| Check | Actual result |
|---|---|
| Native CTest | 22/22: 19 CPU tests, the CUDA error classifier, and two hardware tests |
| Native injected resource matrix | 301 injected trials, zero failures; all tracked buffers/events/plans released, plus four session ownership/re-entry sequences with zero failures |
| Healthy tutorial vs current main | 24 MRC files, 25 STAR files, **341,735,520 pixels exactly equal** |
| Healthy early binning vs current main | factor 2, DW/noDW/even/odd: 4 MRC, 2 STAR, **262,144 pixels exactly equal** |
| Actual runner retry reset | first local attempt injected nonconvergence with nonzero estimates; actual retry vectors were zero and the second native alignment converged |
| Fatal consumed fallback preparation | allocation ordinal 35, max_iter 1: failed with original cudaPreparePatch attribution; no subsequent allocation #36, no image/joint STAR, zero tracked allocations/stale releases |
| Recoverable same boundary | same ordinal, recoverable status: completed one image, zero tracked allocations/stale releases |
| Patch scratch throwing path | ordinal 34: failed, no image/joint STAR, zero tracked allocations/stale releases |
| Retained early-binning frame cache throwing path | ordinal 19: failed, no image, zero tracked allocations/stale releases |
| Middle-movie failure/non-prefix resume | a/c completed, b failed at ordinal 129; no joint STAR; zero tracked allocations/stale releases. Resume processed only b, preserving a/c image/STAR hashes and mtimes. Final 3 MRC/4 STAR/**786,432 pixels** exactly matched the healthy reference |

The resource matrix sweeps actual call ordinals for allocation, H2D/D2H/D2D copy,
memset, synchronization, event create/destroy, cuFFT create/planning/work-area/execute/
destroy and **cudaFree after physical release**. Scenarios include host staging,
resident preparation, alignment, cache growth and dose-weighted reconstruction.
Cleanup errors during documented best-effort teardown may be survived; the matrix
does not require every injected cleanup error to abort a completed numerical result.

The four session sequences exercise: recoverable first free followed by consumed fatal
free (clean runtime slot, sticky refusal and idempotent release); second group allocation
failure followed by success; cache free failure followed by success; and cache planning
failure followed by success. A poisoned session refuses working-method re-entry and
initialize even after release. No cudaDeviceReset is used.

## Discriminating controls and their actual revisions

All final positive rows above ran at 078ec54. Mutation controls performed before the
last movie-cache guard are retained at their actual revision; these are not relabelled
as final-source trials. The affected translation units otherwise remained unchanged,
and the complete positive matrix was rerun after the final change and after restoration.

| Mutation | Source used | Observed rejection |
|---|---|---|
| Restore pre-repair alignment ownership | 0c13ce0 with a9f20ba alignment | 298 trials, 126 failures, owned-resource leaks |
| Restore pre-repair resident cache replacement | 0c13ce0 with a9f20ba function | 299 trials, 8 failures |
| Remove actual runner shift reset | 0c13ce0 | native caller control reports stale first-attempt shifts and fails |
| Remove fallback helper recording | acb2f40 | incorrectly completes an image instead of refusing the consumed fatal status |
| Remove sticky session entry refusal | acb2f40 | matrix 301 trials, 1 failure |
| Restore first-free-only error recording | acb2f40 | matrix 301 trials, 1 failure: later fatal cleanup masked |
| Remove patch scratch guard | acb2f40 | failed movie retains one tracked allocation |
| Remove retained frame-cache guard | **078ec54** | failed early-binning movie retains one tracked allocation |

The initial expanded harness compile failed on an erroneous global statement; its
diagnostics are retained in build-first-failed.log and the error was corrected before
any accepted test. Existing compiler warnings remain in the retained build output.
The first middle-failure probe used ordinal 128, which hit a recoverable preparation
allocation: production correctly recovered and completed all three movies. That probe
failed the intended failure oracle and is retained separately, not counted as the resume
PASS. Ordinal 129 targets the actual throwing alignment path.

## Provenance and comparison scope

Venue: shared 4-gpu-vm, one A100 80GB PCIe, CUDA 12.8/sm80. Only physical
**GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598** was made visible. Child processes
inherited CPUs **112-119**, OMP_NUM_THREADS=4, runner j4; builds used j4 and the build
lock. Device work held /tmp/motioncorr-gpu2-correctness.lock. Occupancy was checked;
other GPUs/processes were left alone. Release compute inventories are empty.

[Evidence](evidence/ownership-20260929/README.md) retains commands, source IDs,
binary/input hashes, actual payload PID/start/executable/affinity, topology, memory
policy, load, complete matrix results, mutants and native comparison reports. The
earlier provenance-final.txt describes the 0c13ce0 run, not the final source; final
identity is in executed-source-v5.txt, executed-binaries-v5.txt and payload-final.txt.
The latter observes the actual motioncorr executable (PID1788658), not its launcher.
Mems_allowed 0-1/default policy does **not** demonstrate allocation locality.

Comparison requires the exact MRC/STAR file set and payload sizes. All MRC pixel bytes,
all 1024 header bytes, extended headers and labels are compared. Only the validated
19-byte RELION writer timestamp in label zero is normalized. STAR comparison replaces
output directory roots only. The four early-binning products were also rechecked with
the final observed payload. Logs/PDFs are outside this artifact gate. Same-backend exact
output is separate from CPU agreement, upstream parity, known-truth scientific tests
and performance.

## Remaining untested or limited classes

* Genuine illegal-address/ECC/driver-poisoned contexts: statuses are injected; shared
  hardware was not deliberately poisoned. A clean cudaGetLastError slot is never used
  as a health certificate and no reset is attempted.
* Free/destroy errors **before** physical release: tested errors occur after the actual
  release. Pointer/handle invalidation prevents stale retry, but the application cannot
  guarantee reclamation when the driver refuses to free an allocation.
* cuFFT internal workspace allocations are outside interposed cudaMalloc accounting.
  Actual plan handles and their destruction are tracked.
* Natural F5 first-nonconverged/second-converged witness remains unreproduced. The new
  caller test injects the first estimate and runs the real second alignment; it does not
  rewrite that historical limitation.
* The legacy/nonresident path has healthy early-binning and a real throwing cache
  control, not an exhaustive independent fault sweep of every streaming FFT stage.
* Older toolkits, other GPU hardware and float-host builds were not executed. The
  caller interposition is explicitly for this double-host ABI.
* No PR93 optimization or subsequent U16 work is approved by these results. Latest
  source independent review and integration remain outstanding before merge.
