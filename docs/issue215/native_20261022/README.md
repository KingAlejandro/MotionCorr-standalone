# PR248 native later-chunk controls, 2026-10-22

Implementation worktree: `t3-409be643`, branch
`work/248-native-laterchunk-20261022`, pinned source
`fc1c8e6f18fe1f33d4a7cc68da2fbc467bd01c16`.
The parent/root checkouts and historical evidence are untouched.
Issue215, PR248 body/review and inline discussion were read live before work;
the captured discussion is retained here.

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

## Allocation and limits

Only GPU2, UUID `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, CPUs8–9,
numeric/OpenMP threads1; compile `--parallel 2` under
`/tmp/motioncorr-build.lock`. The driver holds
`/tmp/motioncorr-gpu2-correctness.lock` nonblocking for preflight/run/health,
probes `/tmp/motioncorr-bench.lock` nonblocking and immediately releases it,
and rechecks index/UUID and absence of assigned-GPU applications.
No timing/performance comparison, production policy/math change, push, merge,
GitHub comment or Notion write is part of this work.
