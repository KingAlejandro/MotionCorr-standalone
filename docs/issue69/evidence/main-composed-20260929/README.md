# Current-main combined acceptance — 29 September 2026

## Pinned composition

- Tested source: `0f2ddd5dbb0a4be7af5f63884cd29cd68ef8def1`; `src` tree `5fb86b90337c7dc606f40b15d7950c821cb1060a`.
- Includes main `6393547e` (PR114 recentering) and the reviewed enumeration and
  preprocessing session-disposal fixes. History was merged/cherry-picked with
  provenance; no force push or obsolete PR93 CUDA history was used.
- Additive merge conflicts retained both the test friend declaration and public
  interpolation/recenter helpers. The complete required-test union is 21
  CPU-required names; every per-name negative control remains registered.
- Both exact-source GitHub checks passed: [Build & Smoke Check (Ubuntu Linux)](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/36578045213/job/109438661300); [CUDA compile only (no GPU execution)](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/36578045213/job/109438661750). The CUDA CI job is compile-only;
  the following hardware executions are separate evidence. The final evidence
  commit changes only documentation; its own CI should be checked before merge.

## Executed acceptance

- **Native CTest 26/26 PASS**, no failed tests. This includes CPU-mode
  regression/negative controls, recenter arithmetic and end-to-end CPU interpolation,
  the native `RunnerInterpolateShiftsCuda`, ownership matrix, preprocessing failure
  controls, upload failure and CUDA error classifier. CTest's complete command/output
  log and collection JSON are retained. The explicit required-inventory gate passes.
- Both branches' registered native recenter case was corroborated with retained
  option-off/on products: selected original frames 2–8, groups {2,2,3}, nine native
  converged patches per arm, unchanged anchor/linearity/serialization assertions.
  Actual executable/PID/start/CPU-mask/NUMA maps and physical GPU UUID are recorded
  for both payloads. PR114's old-source rejection and option-off product comparison
  remain earlier-source evidence; they were not repeated or relabeled here.
- **Preprocessing: 8/8 cases PASS**. Both healthy input types and recoverable sparse
  failure complete; recovered full MRC headers/pixels and both STARs are exact.
  Fatal initialize/sparse/gain/forward-FFT and recoverable-then-fatal-release cases
  fail before new allocation, host materialization or image/STAR publication.
  Operation/cleanup attribution and zero owned/stale allocations are checked.
- **Enumeration: 10/10 executions satisfy their expected outcomes**. Runtime
  discovery finds session initialization at query2 and patch preparation at query5.
  Fatal returned statuses survive clean last-error slots and fail without products;
  four recoverable/zero-device controls match healthy full normalized MRC headers,
  both STARs and all 14,238,980 pixels. Owned resources are released.

## Resources and release

Device `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, CPU mask 112–119, all descendants limited to eight logical CPUs.
Standalone preprocessing/enumeration runtime j4/io2; recenter runtime j1. Other
registered CTest cases retain their specified settings within the inherited mask.
Build j4 under exclusive `/tmp/motioncorr-vm-build.lock`; hardware
runs held their device correctness lock. Main composition work ran on disjoint
GPU0/GPU2 masks. Memory policy was host-default: no NUMA allocation-locality inference.
Actual payload identities, topology, available disk, compiler/driver, UUIDs, source,
input, binary and helper hashes are retained. Final release: **Tue Sep 29 13:54:05 UTC 2026**.
Postrun compute and project-lock inventories are empty. No unrelated process was
stopped, no device reset occurred, and these are not controlled performance runs.

## Limits and provenance

No full24, new throughput/RSS series, science suite, older-toolkit run or genuine
context poisoning was added. Existing all24 and mutants remain attached to their
original source heads; this bounded composition does not relabel them as fresh runs.
PR118's reproducible previous-source +0.230 GiB no-gain RSS increase and pending
support work remain open; this acceptance does not justify a memory-saving or
promotion claim. Earlier raw failures (archive-only Git diagnostic, local missing
NumPy, comparison setup, scientific/auxiliary artifacts) remain preserved.

The archive SHA-256 is `e606439125240d0c9c44d50aa3c82d256bd6608fde1931df9fefcf6f79e9f5ad`. Full image/TIFF/binary artifacts remain under
`/home/alex/mc-pr115-enumeration-20260929/main-proof`
and its sibling build directory; all image/input/STAR hashes are in `data-sha256.json`.
Git retains the compact command/log/product-STAR/process/comparison evidence.
