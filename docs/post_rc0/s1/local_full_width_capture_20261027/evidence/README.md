# Evidence: full-width two-patch capture extension (build and checks only)

**Source under review:** commit `f473fbc9c380c7bb8cc1533f19461fbf70dde485` (tree `f23ed001`); design freeze `4ad43a3f`; first source commit `dd2a92bb`. Pinned diff `source.diff` (src and tests, 4 files, +139/-19; sha256 in `source.diff.sha256`) against `4ad43a3f`. `src/local_ccf_capture.h`, `src/motioncorr_runner.cpp` (guard term removed, mode and actual `weight_x_norm` passed), `tests/test_local_ccf_capture.cpp`, `tests/test_local_ccf_capture_cli.py`. No CMake, CUDA, dependency, arithmetic, weight, reference, peak, stopping, fitting, default or publication change.

**Build:** exact `git archive` of `f473fbc9` (12282 files, 0 mismatches against git blobs), CPU Release, `-DMC_EXPERIMENT_CCF_DC=ON`, no CUDA, AppleClang 21.0.0, CMake 4.4.4, `-j2`, OMP/BLAS threads 2, CPython 3.13.7 / NumPy 2.4.2; identity and hashes in `r2/BUILD_IDENTITY.txt` (motioncorr `c71fe7f9…`, local_ccf_capture `41319c7a…`). Preflight (load, disk 28 GB free, 24 GB RAM): `r2/PREFLIGHT.txt`. Build exit 0, no warning in the touched files.

## Results (all in `r2/`; commands in `verify_all.sh`)
| Check | Result |
|---|---|
| `LocalCcfCapture` unit (extended: legacy bytes, pair selection, metadata, failures with controls) | PASS |
| `LocalCcfCaptureCli` (legacy control, full-width reaches the missing-input error, refusals before movie access, capture-off path) | PASS |
| Same unit test built with AddressSanitizer + UBSan | PASS |
| Legacy differential: pre-change header (`4ad43a3f`) versus new header, same dump program, 606 files each | byte-identical (`diff -r`; file hash listings equal) |
| ctest: LocalB2Fit, CcfDcHook, ExperimentalFlagsCli, LocalFullWidthWeight | PASS |
| ctest: PatchRetryState, GlobalHalfGain, CoupledPeak, IsotropicWeight | ABORTED without a DC arm (as before, launcher omission); PASS with `MC_EXPERIMENT_CCF_DC_ARM=none` (both logs kept) |
| Mutants: wrong coordinate, no duplicate guard, no weight-normalisation check, legacy schema changed, no missing-patch check, no centre/extent check; guard still refusing the flag (CLI) | each fails its named test; unmutated control passes |

## Limitations and UNRUN
Compilation and these checks establish nothing about native capture, neutrality of the new binary, or science. UNRUN: the two producer checks (capture OFF with local full-width ON against the sealed full-width ON baseline; then capture ON against that new OFF), any native movie, CUDA, GPU, the exact Hermitian/uninitialized-memory sanitizer (MemorySanitizer is unavailable on this host; uninitialized rejected-offset reads are covered by member initializers, `reset()`, the null-offset assertions and the ASan/UBSan run), and all analysis. Only one local macOS arm64 toolchain was used. Failed and superseded attempts are in `attempts/r1/` and `../AMENDMENTS.md`.
