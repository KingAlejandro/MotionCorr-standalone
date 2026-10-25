# C1 bounded native completion, 25 October 2026

Tested production source remains `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`; this packet adds qualification tooling/evidence only. Main and production gates/defaults are unchanged. No scientific, performance or aggregate C1 PASS is claimed.

| Row | Observed result |
|---|---|
| R9 CUDA and nvCOMP | Each16/16 cases PASS;28/28 native arms witnessed on GPU3. Expected negative exits remain in the records. |
| #249 CUDA/nvCOMP × bz2/xz/zst | Each12 cases, no failures (72 total), including late decoder failures, explicit subsets and healthy controls. Float ingest exercises compressed-reader status; this is not genuine nvCOMP-ingest poisoning. |
| D12 tutorial G and L | Native endpoints PASS/ready with24 movies, one witnessed GPU3 worker, complete cleanup. Both original strict comparisons FAIL/INVALID on the archived `_workers/w0/corrected_micrographs.star`. Separate v1.1 grades prove49 canonical products IDENTICAL and separately verify the full archive. |
| K267 CUDA | Eight native exits0; checker1 PASS /5 FAIL /2 UNIDENTIFIABLE. Noisy/repeated sampling remains OUTSIDE_FIXED_ROI, estimated image metrics null where invalid. These are new CUDA results, not doubled CPU results or a science PASS. |

## Versioned tooling repair and review

The standalone comparator correctly rejected an undeclared extra STAR. The dataset producer deliberately retains fixed-name worker aggregates under `_workers`. The new read-only helper derives the exact archive from retained worker trees, checks bytes against worker originals and the joint STAR exit digest, checks the aggregate's preserved-file inventory and refuses unexpected archive STAR/MRC or symlinks. Only after that validation does the unchanged strict comparator/classifier compare the canonical49 products. Nothing is deleted, rewritten or silently ignored. All original FAIL receipts remain.

Sonnet5.5 authored the helper; Sol independently reviewed archive derivation, scoped filtering and controls. Four original control groups passed locally. Version1 failed before comparison on Linux Python3.12 because file-loaded dataclasses needed `sys.modules` registration. That attempt and exact v1 are retained. Version1.1 changes only module registration/cleanup and its version; five groups independently pass on Python3.12.11 (author also3.15.1), including the base failure, unexpected archive/product negatives and filter restoration. G was graded read-only without native rerun. L then ran once; its expected old comparison failure and separate v1.1 grade are both retained.

The G read-only grade checked the lane lock, affinity, RAM and scratch before comparison; its explicit process/GPU occupancy snapshot was collected immediately after the short grade, rather than before it. This is a resource-admission receipt limitation, not benchmark evidence. The subsequent L/K267 launch has fresh CPU busy sampling, RAM/scratch/apps checks and per-stage GPU health. CPU8–9 only, GPU3 UUID `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, two threads. No foreign process was terminated. Xid inspection remains UNRUN.

## Evidence and exact remaining work

`c1-i6-i7-receipts.tgz` retains1240 selected receipts/logs/STAR files; `COLLECTED-INDEX.json` inside binds every copied byte and original VM path. Raw MRC payloads remain in the original VM scratch, unchanged. `PARENT-GRADE.json` and separate G/L grades expose the inner results. Tool/source/binary hash checks and all failed attempts remain included. Existing381/381 CTests and prior CPU/T24/R12/route evidence retain their tested source identities; no full audit was repeated for this tooling-only change.

Still UNRUN/held: S1 genuine sticky-context native rows (need>=4 CPUs; fixed lane has2), A13 real-data item13 (`--j8`), K269 CUDA100-movie and K272 image census (no broad new census authorized), multi-device2/4-worker and UUID-selective poison/publication rows (fixed lane GPU3 only), genuine nvCOMP ingest poisoning and kernel Xid inspection. Earlier-SHA seven-family/fallback/EER/ASan/SCARF/soak/performance evidence is not promoted to this candidate. No blanket waiver or M1 recommendation is implied. Next engineering decision is a scoped resource allocation or explicit limitation disposition for these named gaps; W4 research proceeds independently.
