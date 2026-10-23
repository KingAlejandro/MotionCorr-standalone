# Issue #226 post-RC0 memory admission

PR #252's later retry-lifetime correction is documented in
[retry-admission-review.md](retry-admission-review.md). The native results below
retain their recorded revisions and do not qualify that follow-up.

Base: `c8844894c7c6366abf297699b5312e4b775eb5b0`. Implementation head: `bb34855434e0293ad559781697610d742765ebcd` (supersedes the incomplete estimate at `124a8708`). D1 is already fixed.

D2 queries the cuFFT work sizes for the actual patch R2C and alignment C2R
plans with device work allocation disabled. Admission includes the grouped real
patches, their full spectra when they cannot borrow the inverse tile, the CCF
windows and alignment buffers, both work areas, and grouping/shift arrays.
The check follows preprocessing so the existing gain/sum fallback remains first.
On decline, the corrected real frames are downloaded before the resident session
is released; the existing streaming FFT and alignment paths then consume them.
The failure classifier checks and clears recoverable pending errors at disposal.
No floating-point operations or tolerances change.

A non-converged patch also needs an additional full-spectrum stack for the
resident retry. Its admission is checked only once a retry is required, so a
converged neighbouring run keeps its route. If it does not fit, both globally
aligned real and Fourier frames are copied to the host before session release;
the existing streaming retry and reconstruction consume them.

The existing batch-selection policy is unchanged. Workspace byte counts are
local to admission; no new runner or session data members are introduced.
`CudaLocalAdmission` uses a 512-square, 24-frame session and a wrapped memory query
to test zero headroom and the exact required-minus-one/required/required-plus-one
boundary using real cuFFT plan sizes, without occupying an entire GPU.

## Harness

Apply `../qm_batch.patch` to `docs/rc0/qual_qm_vram/harness/qm_batch.py`. It changes only
scratch/build/run paths and replaces visible-device ordinals with the original
QM UUID. Both arms use this same adapted harness, the same movie inputs and GPU.
The original balloon binary is copied from W-QM (source `qm_balloon.cu`).
Use `QM_BUILD=build-unfixed QM_RUNS=runs-base` for the base binary, and
`QM_BUILD=build-d2-bb348554 QM_RUNS=runs-d2-bb348554` for D2. Run inside
`flock /tmp/motioncorr-gpu1-correctness.lock taskset -c 104-111` with
`/home/alex/.mc-venv/bin/python3 -I qm_batch.py <specs>`.

## Measured result

On implementation `bb348554`, all 15 constrained cases pass the existing strict
product comparison. The same predicate on unfixed `c8844894` fails at exactly six
D2 points. The three unconstrained references also match across revisions.

| Family, config L / auto | Reproduced failure → identical completion (GiB) | Previously passing controls, unchanged route (GiB) |
|---|---|---|
| 10441 | 37.5, 38, 38.5 | 36.5, 37, 39 |
| 10474 Falcon 4 | 19, 19.5 | 18.5, 20 |
| 10216 | 8.5 | 7.5, 8, 8.75, 16 |

Both arms contain 18 runs (three unconstrained, 15 constrained). The 16 GiB
control retains batch chunk size 4; all passing neighbours retain their ingest,
CPU-preprocessing and batch policy. Only the failing bands decline resident
local/retry admission. Completed MRC payload/header bytes and motion/joint STAR
products match using the existing comparator, including its existing writer
creation-timestamp mask; no gate or tolerance changed. This is same-backend
product identity, not scientific equivalence or a performance qualification.

Single-run peak host RSS in the newly completing fallback cases was 41764–41765
MiB (10441), 26417–26447 MiB (Falcon 4), and 8001 MiB (10216). The mandatory
admission fallback retains compact host staging until movie completion; these
samples are not a host-memory bound or a guarantee on smaller-RAM machines.
The resident-L floors remain 39, 20 and 8.75 GiB respectively. The historical
QM floor table is not a measurement of this candidate.

Release full CTest passes: CPU **74/74** on cpu64 (CPUs 0–7), CUDA **109/109** and
CUDA+nvCOMP **112/112** on 4GPUs (CPUs 80–87, GPU2 UUID
`GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, per-GPU lock). Required-test collection
checks and every recorded configure/build exit are zero. `CudaLocalAdmission`
is included in both GPU suites. Actual compilers are GCC 13.3.0/CUDA 12.8,
nvCOMP 5.3.0.16, A100 80 GB PCIe/driver 570.86.10. All work uses an eight-CPU cap;
occupancy was checked and unrelated work was left alone. Balloon processes were
reaped after each run. Native cases use GPU1 UUID
`GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d` in both arms.

## Retained receipts and reproduction

- `native.json`: exact commands, input identities, observed free VRAM/RSS,
  completion, route witnesses, product-comparison and cleanup receipts.
- `grade-before.{json,exit}`: six discriminating failures, exit 1;
  `grade-after.{json,exit}`: 15 passes, exit 0.
- `validation.json`: source/binary hashes, resource identities, cross-reference
  comparisons (three exit 0), input hash verification and suite exits.
- `raw-logs.tgz`: original/candidate stdout, timelines, per-movie logs, STARs,
  comparator reports, full build/CTest logs, build flags and cpu64 receipts.
  Large movie products are represented by retained strict-comparison receipts.

```
python3 docs/rc0/issue226/grade.py d2 docs/rc0/issue226/d2/native.json --candidate runs-base
# expected exit 1, FAIL at six band points
python3 docs/rc0/issue226/grade.py d2 docs/rc0/issue226/d2/native.json --candidate runs-d2-bb348554
# expected exit 0, PASS at all 15 points
```

Source snapshots were transferred with git archive. Remote synthetic Git metadata
exists only to run Git-backed trusted-manifest tests; it is not the source
revision. CMake caches/flags and archive provenance identify the real build.
The final source rebuilt both GPU configurations after touching changed headers
and sources; no mixed-layout incremental binary is counted as evidence.

Superseded attempts: an initial incremental build used stale class-layout
objects (all reference runs aborted, invalid evidence); clean `124a8708` fixed
five points but still failed at 10216/8.5 on the retry spectrum allocation.
`728f7ada` completed all original 14 points, but its unconditional batch-budget
subtraction could change a passing route. Final `bb348554` removes that budget
change and the extra data member. Those earlier results do not qualify the final
source. Their summaries are retained in `superseded.json`; raw remote campaign
scratch remains under `/mnt/clathrin/alex-motioncorr-226`.

Main `36913740` (#247) was subsequently merged into the PR branch. It changes
only tests/docs, correcting fake CLI compiler-settle controls. Production `src/`
and `CMakeLists.txt` are byte-identical to tested `bb348554`; native/full-suite
rows retain that tested SHA. Current-head CI exercises the updated test.

Re-entry class: CUDA/shared source (§9.4). The native touched config-L ingest,
preprocessing, global/patch alignment and retry rows above and full three-config
CTest were rerun. Full QF, scientific S1, performance, macOS, dataset multi-GPU,
physical smaller cards, host OOM and genuinely poisoned CUDA devices were not
rerun; their previous evidence keeps its original SHA. No upstream numerical
behaviour, notices, dependencies, publication policy or tolerances changed.
