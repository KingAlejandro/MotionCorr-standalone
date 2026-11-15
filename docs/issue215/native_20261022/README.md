# PR248 native later-chunk controls, 2026-10-22

Initial implementation worktree: `t3-409be643`, branch
`work/248-native-laterchunk-20261022`, pinned source
`fc1c8e6f18fe1f33d4a7cc68da2fbc467bd01c16`.
The parent/root checkouts and historical evidence are untouched.
Issue215, PR248 body/review and inline discussion were read live before work;
the captured discussion is retained here.

## Actual result: attempt04 PASS

Iteration worktree `t3-7a8fa0b5`, branch
`native248-settle-attempt04-20261022`, starts at local
`698cddea4faad612cf397f6c7a08c861ca55fef2` without moving another branch.
Live issue215/PR248 discussion was read again and is retained under attempt04;
remote PR248 remained `fc1c8e6f`. This iteration changes only the experiment
driver, its host controls and new evidence/documentation. Parent owns review,
push, PR body and Notion work.

Attempt04 overall driver **PASS**: unchanged later-chunk controls **8/8 PASS**,
unchanged early controls **9/9 PASS**, both subprocess exits0, strict initial
idle/health **PASS**, bounded post-run idle/health **PASS**, and all pinned source,
source-archive, three binary and driver-file hashes **PASS** before/after.
There was no recompilation. All three historical archive hashes also passed
before and after; their FAIL verdicts and bytes remain unchanged.

The explicitly authorized [post-run settling policy](settling-policy.md) requires
two consecutive idle samples, spaced by one second after sample completion,
within a ten-second monotonic window including query execution. The thresholds
remain 0% utilization, no assigned-GPU apps and memory <=16 MiB, with all existing
hardware fields healthy and index/UUID correct. Only nonzero utilization on an
otherwise healthy, empty GPU may settle. Other errors fail immediately and
receive no retry. Initial preflight and all numerical/product gates are unchanged.

Actual post-run sequence was **0%, 0%**, both 1 MiB, no apps, all hardware fields
healthy; the two checks completed within the bounded window. Native execution
therefore did not exercise a nonzero-utilization settling transition.
The fake-clock host controls exercise **6% -> 0% -> 0% PASS**, persistent-busy
timeout, single-idle insufficiency/consecutive-count reset, deadline overrun,
read failure, and immediate rejection of every health field error/missing field,
UUID/index, app and memory violation at each sample position. All eight test
methods **PASS** locally and remotely. The control invokes the original one-shot
driver and confirms it still rejects the initial 6% in a 6%-then-0% sequence.
The existing XML parser controls also **PASS**, rejecting ten altered/missing
health/UUID cases. The unchanged 18-case host acceptance harness **PASS** remotely.

Fresh scratch:
`/mnt/clathrin/motioncorr-215-native-20261022-7a8fa0b5-a04`.
Execution provenance window: 2026-10-22 14:53:04–14:53:30 UTC; native harness
commands ran 14:53:14–14:53:27 UTC. These timestamps are not performance results.
The runner was launched with `nohup env PYTHONDONTWRITEBYTECODE=1
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
taskset -c 8-9 /usr/bin/python3 run_attempt04.py`.
It held the GPU2 correctness lock through strict preflight, both harnesses and
post-health, probed/released the bench lock, and captured occupancy at launch.
No build lock was needed. Exact argv/affinity/exits are in attempt04 receipts.

The compiled source remains `fc1c8e6f18fe1f33d4a7cc68da2fbc467bd01c16` and
binaries remain in attempt01's scratch. [Driver identities](attempt04/driver-identity.json)
record the distinct experiment implementation; [pre](attempt04/pre-reuse-verification.json)
and [post](attempt04/post-reuse-verification.json) receipts verify all 7,260
source files, source archive and all three binaries. An independent local Git
archive reproduced the pinned source/archive hashes. Fixed later-grow/replace
both satisfy the same acceptance predicate; successful nvCOMP mutants both
fail it, while retaining full original MRC/STAR identity. Earlier conversion
again verifies both device destinations against the independent oracle.
See [new witnesses](attempt04-native-witnesses.log).

Attempt04's separately indexed archive has 390 members, SHA256
`931d96145ba4ab369303ce81fd118a550f614c9efe6c9e0e8581c9ca693fb48f`.
It was packaged once, verified on host and downloaded alongside all three old
archives. Every member and compact receipt was independently rehashed.
[Verification](attempt04-archive-verification.json) retains the old FAILs and new
PASS. Reproduce with `PYTHONDONTWRITEBYTECODE=1 python3
 docs/issue215/native_20261022/verify_attempt04.py <download-directory>` where
files are named `attempt01.tar.gz` through `attempt04.tar.gz`.
The verifier does not rewrite historical evidence.

No timings, scientific qualification, full-suite result, newer compiled source,
or reclassification of historical attempts is claimed. The limitations below
continue to apply.

## Retained attempt03 result: driver FAIL

CUDA+nvCOMP compilation **PASS**. Native later-chunk controls **8/8 PASS**;
optional existing early-identity controls **9/9 PASS**. Both test subprocesses
exited zero. The detached attempt03 driver remains **FAIL** because its
immediate post-run *idle* assertion sampled 6% utilization, although memory was
1 MiB and no assigned-GPU applications existed. The hardware fields in that
same post-run XML, captured while holding the original correctness lock, are
**PASS**: zero volatile uncorrected SRAM/DRAM ECC, no pending/failed remap, no
recovery action. A later read-only check under the reacquired GPU2 lock reports
0% utilization, 1 MiB, no apps, and hardware health **PASS**. Before the explicitly authorized attempt04, no further GPU
workload followed that failure. No reset, gate waiver or overwritten original
verdict occurred. See `attempt03/reconciliation.json` and the original `exit.json`.

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
- `/mnt/clathrin/motioncorr-215-native-20261022-7a8fa0b5-a04`: new bounded-driver
  PASS, unchanged 8+9 native controls and all host/identity checks; 390 indexed
  members. Historical archives were read and rehashed, never repackaged.

Every archive member was rehashed after packaging on host and independently
verified after download to local temporary storage. The compact receipts here
are checked against those member hashes. `archive-verification.json` and
`native-witnesses.log` provide the independent verification and extracted
witnesses. The health parser also accepts the retained driver570 XML and
rejects ten altered/missing-health/UUID cases (`health-parser-controls.log`).

## Review follow-up: completion timestamp

Review of `6454879353b2cc492690aa7ae082d549f919563c` found that separate
monotonic reads for the final deadline check and reported elapsed time could
return PASS with elapsed time beyond ten seconds after a scheduling pause.
The driver now checks and reports one completion timestamp. A deterministic
boundary control reproduces the old failure (`10.001 != 9.999`), accepts a
completion at 9.999 seconds, and rejects a completion exactly at 10 seconds.

Host verification uses `PYTHONDONTWRITEBYTECODE=1`, numeric threads1 and
`/Users/alex.konstantinov/.local/bin/python3` with these commands:

```sh
python3 docs/issue215/native_20261022/test_postrun_idle.py -v
python3 docs/issue215/native_20261022/test_receipt_health.py
```

All **9 settling test methods PASS**; all **10 XML rejection controls PASS**.
The [old-code boundary failure](deadline-before.log) and
[fixed settling controls](deadline-after.log) are retained separately; the
text transcripts omit trailing whitespace.
These are host-only checks. Attempt04's original 1.70-second completion,
driver identities, native results and all four archives are unchanged; the
repaired driver has **not** been rerun natively.

## Allocation and limits

Only GPU2, UUID `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, CPUs8–9,
numeric/OpenMP threads1; compile `--parallel 2` under
`/tmp/motioncorr-build.lock`. The driver holds
`/tmp/motioncorr-gpu2-correctness.lock` nonblocking for preflight/run/health,
probes `/tmp/motioncorr-bench.lock` nonblocking and immediately releases it,
and rechecks index/UUID and absence of assigned-GPU applications.
No timing/performance comparison, production policy/math change, push, merge,
GitHub comment or Notion write is part of this work.
