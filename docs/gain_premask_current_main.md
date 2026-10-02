# Gain and premask reuse on current main

Current composition includes main `6c87441d3e44e977994bd26175601092cc344a21`
(130/131/132/137/145 merged); original gain source was based on `57e98666`.
Port the original gain and sparse premask commits `bc695da` / `2dfcc14`, then
the exact-content repair `d3ab07d`, preserving authorship and cherry-pick links.
The remaining PR136 FFT-plan retention and PR140 alternative pool are not imported.

## One retained gain, one live borrower

The worker retains at most one device gain array, keyed by resolved host gain
generation, geometry, byte count and physical device index. It replaces rather
than accumulates entries. Its retained bytes are exactly `nx * ny * sizeof(float)`
for the owned entry: 56,955,920 bytes for the tutorial gain. This is a calculated
component, not a measured whole-process VRAM peak or memory budget guarantee.

One explicit session lease prevents interleaved sessions on the same host thread
from freeing a live borrowed gain. Stale or unused gain is evicted before new
movie-buffer admission, rather than after those allocations. A no-gain movie
therefore retires an unused gain; a later gain movie uploads it again. Generation
zero continues using a session-owned copy. No FFT workspace retention is added.

Cleanup follows the checked device-selection rule independently validated in
PR140: invalidate reuse first, retain ownership/bytes if selecting the owning
device fails, and release only after successful selection. Restore the caller's
device afterward. Fatal retirement is monotonic for the worker lifetime and
preserves the original fatal status for a fresh session, independently of a
cleared CUDA error slot. A retired worker must restart.

Premask lookup compares the exact TXT bytes passed to the parser; image maps
rebuild per movie. Gain-zero union and hot pixels remain separate: detected hot
pixels modify only a movie's deep copy. Sparse traversal preserves row-major
order and random draw order. See `pr136_defect_content_identity.md` for TXT
memory cost, observed-byte versus atomic-file limitations and parser controls.

## Executed and outstanding evidence

Actual-header host doubles exercise owner selection, live lease and sticky
retirement. Exact predecessor source and guard-removal mutants must compile and
fail at named runtime assertions. The entire driver repeats under Python `-O`;
its pinned in-tree predecessor fixture works in a shallow checkout.

Local AppleClang/ARM64 original gain collection has 33 required CPU tests; the main145
composition preserves the union of 34, including `JointStarPublication`. The synthetic
historical-reference test fails identically on unchanged main and the candidate
(max pixel difference 23.649856567, RMSE 0.3119288, shift RMSD 0.003305323 px).
NativeMovieStaging is skipped on this platform. These are not a full CPU PASS;
no tolerance or fixture is changed to conceal either result.

Required before merge: current-head Linux checks and independent source review;
actual CUDA gain lease/failed selection/stale-admission/fatal controls; complete
same-runner premask rewrite/malformed/restoration controls against unchanged-main
native products; all required native configurations; and owned release evidence.
CUDA compile and fresh native execution are currently UNRUN. The dedicated
acceptance uses two GPUs and eight payload CPUs, build parallelism four. Preserve
existing timing campaigns and configured allocation limits.

The historical full PR136 speedup is not a result for this smaller composition.
No fresh performance, CPU–GPU agreement, scientific truth or PDF-content claim
is made here. A later matched benchmark must time and grade the complete product.

Main145 composition `b78709b322fe301b2558ae4d62275995c20998bf` preserves
reviewed gain/CUDA/premask production unchanged, imports checked joint STAR
publication exactly from main, and retains both missing-name negative controls.
SCARF3522232 is queued at the frozen earlier `4cdbc796` source. Its result must
remain pinned there; current-composition native acceptance is still unrun.
The earlier pending job3522120 was cancelled before allocation after a harness
PID/birth ownership flaw was found; corrected host controls and independent
harness review passed before one standard resubmission. No quota limits changed.
