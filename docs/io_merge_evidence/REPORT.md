# Frozen PR90/PR91 runtime validation

Completed 2026-09-27. Ownership was evidence and harness only; no production changes or merges.

## Source and execution

| Role | Exact source |
|---|---|
| Immutable baseline main | `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` |
| Standalone PR90 | `7a4f93f782a970fd146527beb5fd49e64695c1dc` |
| Combined PR90 plus PR91 | `e4f6769b0e1eb565fb1aed8de760efe1e6dc86f6` |

CPU: `small-refmac-machine` via cpu64, top-level affinity48-55, builds <=8, healthy runs j4, Release CUDAOFF/TIMINGON. PID2967312 and supplementary component PID2977184 completed. Runtime, build logs, source and executable hashes are under `raw-cpu/evidence`.

CUDA: dedicated exclusive SCARF job3510669 on gn3000, A100 SXM4 40GB, CUDA12.8.61, GCC11.5, Release CUDAON/TIMINGON/sm80, builds<=8, device0, j8. Completed0:0. Runtime/build/device-process and resident-stage witnesses are under `raw-gpu/evidence-3510669`. Allocation requests were GPU1/cpus8; exclusive allocation provided the whole node but runtime used one device.

Baseline source cleanliness, executable hashes, prior complete output-validation provenance and CMake caches were checked before reuse. Baseline was not rerun unnecessarily. All24 current CPU movie SHA256 values match the retained SCARF input content manifest (`input-provenance-comparison.json`). Gain/input STAR hashes are in both evidence trees.

## Required real-data outputs

Both new heads processed all24 tutorial movies natively on CPU and CUDA. Each baseline/new-head comparison passes:

- 24 corrected MRCs, **341,735,520 pixels**, exact ordered pixel identity.
- Stored MRC payload byte SHA256 identity for all24 outputs, independently of float tolerances.
- Normalized MRC headers exact under the existing clock-label normalization.
- All25 STAR artifacts match; all24 per-movie original exact gates pass with complete coverage.
- Targeted missing-output, pixel-bit change, non-clock header change, and wrong-output-root STAR controls detected.

CUDA standalone/combined also directly compared with each other: same complete pass. Both CUDA runs have sampled native motioncorr device processes and all24 per-movie resident FFT/global reconstruction/local alignment/dose-weight witnesses. This establishes execution of the resident CUDA path, not selection alone.

The full comparator's **overall FAIL remains preserved** because four auxiliary PDFs differ. Required numerical/header/STAR `overall_graded` is PASS. No auxiliary logs or algorithm outputs failed. PDF byte identity is not claimed.

## CPU checks and reader controls

- Standalone CTest12/12, combined CTest13/13, both rc0.
- Ordered decoded-buffer controls3/3 each: u16 deflate rows-per-strip1, u16 raw multistrip/final partial strip and two frames, genuine packed4 recognized detector geometry with multistrip data. **56,960,739 float32 pixels** exact for each build against frozen main; row-preserving pixel permutation, bitflip and missing controls detected.
- Original helper was O2. Separate helper compiled using each product's exact generated core CMake flags (**O3 DNDEBUG TIMING C++17 OpenMP**) repeats all three decoded cases and strip controls successfully. Original O2 reports are retained rather than overwritten. Actual healthy production runs always used Release binaries.
- Test-only libtiff returned-count injection covers zero, positive partial-row, oversize, last-strip short-frame and over-height. Both heads reject all five with a caught non-signal error, specific source rejection, no completed dump and rejection before entering the second frame. These are targeted reader-component checks, not a claim of real malformed encoded-strip fixture coverage or native whole-pipeline fault injection.

## PR91 failure and resume contract

Combined head:

- Missing, corrupt-header and hard1MiB truncated TIFF cases, damaged first and last, j1 and j4: **12/12 graded cases PASS**, zero signal deaths. Healthy output retained; error names damaged input; nonzero failure and failure marker; no misleading joint output or success marker.
- Resume j1 and j4: each initial failure7/7 checks, unfinished retry8/8 and repaired success9/9. Healthy MRC/model content SHA and mtime remain unchanged across retry and repair; damaged input is retried then repaired; final joint coverage/success marker correct.
- Additional artifact-only retained healthy output check across all16 damaged-run trees and both repaired resume trees: **18/18** exact pixels, normalized headers, model metadata and literal payload bytes against existing main output at matching j1/j4.

Four longer truncated-prefix cases remain explicitly **observation only**. libtiff reads an eight-frame directory chain from what was originally24frames; all four invocations accept8frames and return success with joint output. Per-frame decoded-strip bounds do not detect a missing tail of otherwise readable TIFF directories. Preserve this limitation as a separate follow-up; do not claim arbitrary truncation is detected.

## Evidence and interpretation

- CPU archive `io-merge-cpu-evidence.tar.gz`: SHA256 `97e72ecb613c7b301896e625a34a182ef8f5c47320adcfa27ba205859468ddd0`.
- CUDA archive `io-merge-gpu-3510669-evidence.tar.gz`: SHA256 `c5803110a8c27991ef2615b0aa603f0901080d9bfa8da8fa676d1a50a3156145`.
- `manifest.json` pins sources, hosts, scripts and limitations. Original report failures, raw logs, commands, gates, artifacts and controls remain available. Large MRC payloads are retained remotely; compact archives retain their exhaustive comparison and SHA evidence.

No new controlled benchmarks were run. Existing performance numbers from source676f763 are historical and are not reattributed to these final source heads. Results demonstrate same-backend regression and the specified failure/resume contract; they do not establish CPU/CUDA agreement, historical RELION Gate2 or scientific equivalence on independent collections.
