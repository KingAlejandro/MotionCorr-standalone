# PR248 native later-chunk controls, 2026-10-22

Implementation worktree: `t3-409be643`, branch
`work/248-native-laterchunk-20261022`, pinned source
`fc1c8e6f18fe1f33d4a7cc68da2fbc467bd01c16`.
The parent/root checkouts and historical evidence are untouched.
Issue215, PR248 body/review and inline discussion were read live before work;
the captured discussion is retained here.

## Actual result

CUDA+nvCOMP compilation **PASS**. Native later-chunk controls **8/8 PASS**;
optional existing early-identity controls **9/9 PASS**. Both test subprocesses
exited zero. The detached attempt03 driver remains **FAIL** because its
immediate post-run *idle* assertion sampled 6% utilization, although memory was
1 MiB and no assigned-GPU applications existed. The hardware fields in that
same post-run XML, captured while holding the original correctness lock, are
**PASS**: zero volatile uncorrected SRAM/DRAM ECC, no pending/failed remap, no
recovery action. A later read-only check under the reacquired GPU2 lock reports
0% utilization, 1 MiB, no apps, and hardware health **PASS**. No further GPU
workload, reset, gate waiver, or overwritten original verdict followed that
failure. See `attempt03/reconciliation.json` and the original `exit.json`.

These results qualify this small valid-body fixture and instrumented binaries.
They do not qualify arbitrary corrupt Deflate, performance, Tier D science,
multi-GPU behavior, a full suite, or a newer source revision. No production
source or existing numerical/identity predicate changed.

## Native acceptance evidence

Run window: 2026-10-22 14:39:00–14:39:14 UTC on `4-gpu-vm`. The new harness
ran 14:39:00.751–14:39:07.257 UTC; these receipt timestamps are provenance,
not a performance measurement. `attempt03/later-controls/result.json` records:

- Two compact references: original and replacement, both **PASS**.
- Fixed and mutant healthy rows: route `nvcomp`, successful completion,
  complete original MRC/STAR identity, both **PASS**.
- Fixed later append and atomic rename: verified earlier conversion,
  ordered mutation witnesses, named production identity decline, route
  `compact`, and complete appropriate-reference MRC/STAR identity;
  `fixed_acceptance=true`, both **PASS**.
- First-chunk-only mutant append and rename: the **same fixed predicate**
  rejects each (`fixed_acceptance=false`), while each process exits zero,
  stays on `nvcomp`, emits no identity decline, and matches complete original
  MRC/STAR products; both negative-control verdicts **PASS**.

The actual first kernel launch is identified by its host-stub address. Its
stream is synchronized, then **all 3,840 frame pixels and 1,920 accumulated-sum
pixels** exactly match the independent Python float oracle. Only afterward
does span-read index4 trigger mutation. Each conversion/read/mutation witness
appears exactly once, in order. The fixed rows therefore exercise fallback
after partial device accumulation, not merely before decoding. The product
comparator checks MRC inventory/geometry/header/extended header/payload and
both STAR products, with only its existing output-root and MRC writer-time
normalization. Logs/PDFs are outside that identity gate.

Input: 48x40x6 uint16, valid Adobe Deflate, two frames/chunk, one reader, no gain.
Original TIFF SHA256:
`b44a1e6220b22b89638705fd83beabf44f662c54bbd0509b302af4f759acbb3e`.
Replacement SHA256:
`fba0d3d9c55ac6432c8d5a0a0ad75cf670c24e22b8e327acb438e11493dea611`.
Append adds 16 bytes; rename replaces the path with the valid +1-pixel fixture
while the reader handle remains on the original inode.

## Revisions, tools and commands

The native source is exactly `fc1c8e6f18fe1f33d4a7cc68da2fbc467bd01c16`.
All 7,260 archived source files were independently rehashed against the local
Git archive before native execution. The seven Python bytecode files generated
by host checks are separately indexed; no archived source file changed.
Binary hashes were verified before the run and after reconciliation:

- `motioncorr_tiff_identity_later`:
  `f09f4d9a6b7c697148cee9cbb54121758bfaae21de53e2972a9bd5dd997379ba`.
- `motioncorr_tiff_identity_first_chunk`:
  `f6161b81d17da4ff63e8f48e854176acc6ee578779c2718da03f673a59b39a34`.

Software: Ubuntu GCC13.3.0, CMake3.28.3, CUDA12.8.61, driver570.86.10,
nvCOMP5.3.0.16 at the discovered existing root
`/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive`,
and discovered Python `/home/alex/.mc-venv/bin/python3` with NumPy2.5.3.
The loaded nvCOMP library and header hashes, `ldd`, CUDA version, paths,
configuration and complete build logs are retained in attempt01's archive.

The detached runners were launched as
`nohup taskset -c 8-9 /usr/bin/python3 run_native.py` (build/attempt01) and
`nohup taskset -c 8-9 /usr/bin/python3 run_retry.py` (attempt03, verified reuse).
All subprocesses inherited affinity8–9 and numeric/OpenMP threads1.
Exact configure/build argv/exits are in `attempt01/configure.json` and
`build.json`; both exits0. Native parent argv/exits are in
`attempt03/later-controls.json` and `early-controls.json`; both exits0.
Every movie's complete argv/exit is in the corresponding `result.json`.
The retry uses the unchanged source and binaries built in task-owned attempt01
scratch; there is no second compilation or source transfer masquerading as a
fresh native binary. The optional nine-row harness uses that same fixed binary
and the already generated independent conversion oracle.

## Attempt 01: build PASS; launch receipt FAIL; native UNRUN

Fresh scratch on `4-gpu-vm`:
`/mnt/clathrin/motioncorr-215-native-20261022-409be643-a01`.
The exact pinned Git archive SHA256 is
`121a5adcf8379a5dceef1d5f0680debb127b499f17436a3495d15d5b92282499`.
CUDA+nvCOMP configure and compilation of both new instrumented executables
**PASS**; remote host controls **4/4 PASS**, including all 18 fake-CUDA cases.
Local configure/build and the same four focused host checks **PASS**.

The detached driver PID 2979330 completed and released its locks. It stopped
before native test execution because its receipt parser expected
`ecc_errors/volatile/uncorrected/total`, absent in driver 570.86.10's XML.
The retained XML instead reports zero for `sram_uncorrectable_parity`,
`sram_uncorrectable_secded`, and `dram_uncorrectable`, with recovery action
`None`, remap pending/failure `No`, and idle GPU2. This is a receipt-parser
failure, not an observed GPU hardware failure. Attempt01 remains **FAIL** and
its native tests **UNRUN**. No reset or gate waiver was performed.

The raw archive remains on host and all its 170 indexed members were rehashed:
`attempt01/archive.json`, `attempt01/raw-index.json` retain its path/hash.
Initial system-Python discovery also failed because NumPy was absent; see
`discovery-failure.json`. The existing venv was then verified, without changing
the shared environment.

## Attempt 02: source inventory receipt FAIL; native UNRUN

The inventory verifier initially counted seven generated `__pycache__/*.pyc`
files as additions to the immutable source tree and stopped before acquiring
the GPU lock or running native tests. Comparison reproduced the mismatch:
7,260 expected files, 7,267 actual files, **zero modified/missing source files**.
`attempt02/source-mismatch.json` records all seven added bytecode hashes.
The corrected verifier compares every original source byte against the pinned
archive and separately permits/records only those generated `.pyc` files;
future subprocess bytecode writes are disabled. Attempt02 remains **FAIL**,
native **UNRUN**, and its archive is retained unchanged.

## Retained archives and checks

All raw products, fixtures, oracle bytes, process/movie logs, route witnesses,
commands, locks and failed-attempt evidence remain on 4GPUs. No binary, TIFF,
MRC, PDF or raw archive is committed. For each `attemptNN`, `archive.json`
records the absolute archive path/size/SHA256 and `raw-index.json` records every
member's size/hash. The archive directories are respectively:

- `/mnt/clathrin/motioncorr-215-native-20261022-409be643-a01`: build and first
  receipt failure; 170 indexed members.
- `/mnt/clathrin/motioncorr-215-native-20261022-409be643-a02`: inventory receipt
  failure; 9 indexed members.
- `/mnt/clathrin/motioncorr-215-native-20261022-409be643-a03`: native results,
  original idle failure and read-only reconciliation; 373 indexed members.

Every archive member was rehashed after packaging on host and independently
verified after download to local temporary storage. The compact receipts here
are checked against those member hashes. `archive-verification.json` and
`native-witnesses.log` provide the independent verification and extracted
witnesses. The health parser also accepts the retained driver570 XML and
rejects ten altered/missing-health/UUID cases (`health-parser-controls.log`).

## Allocation and limits

Only GPU2, UUID `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, CPUs8–9,
numeric/OpenMP threads1; compile `--parallel 2` under
`/tmp/motioncorr-build.lock`. The driver holds
`/tmp/motioncorr-gpu2-correctness.lock` nonblocking for preflight/run/health,
probes `/tmp/motioncorr-bench.lock` nonblocking and immediately releases it,
and rechecks index/UUID and absence of assigned-GPU applications.
No timing/performance comparison, production policy/math change, push, merge,
GitHub comment or Notion write is part of this work.
