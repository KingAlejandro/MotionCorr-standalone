# PR103 review-fix verification — Issue #92

Tested revision: `3037c4bff197e2011f8a5121f4dd32f43047b251`.
Production fix: `433f04ee4ebd879b773fe24f71d5de8696d9efc3`.
Base reviewed PR head: `d8b9758e26fa9ee928a42efbe271f1b8eb0bf64f`.

Source subtree: `93a85598e6406339feb1cf4e212dc47ae189027a`.
Tests subtree: `da858fb0b6f2c5cdcd8652b38269d786e73a1b5c`.
The later evidence/status commit changes neither subtree.

## Results

- Native LibTIFF 4.5.1 handle-local path: full CTest **13/13 passed**; direct damaged-movie suite **11/11 functions passed**, including heterogeneous STAR/CLI precedence, frame-index exclusion, invalid/conflicting counts, filtered resume, stale saved count, and real two-tomogram global counts.
- Compatibility path selected by version-header include shims: full CTest **13/13 passed**. This uses the installed **4.5.1** library; it does **not** establish runtime compatibility with an actual older library.
- Four concurrent header readers, each with 20 healthy and 20 invalid-header reads: zero unexpected failures in both paths; exactly one outside error reaches the previous handler, and one outside warning reaches the preserved warning handler. Branch identities are printed and enforced at compile time in the harness.
- Current tutorial movie `20170629_00021_frameImage.tiff`: **126,550,106 bytes**, SHA256 `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`. Prefixes of **43,748,634 / 8,388,608 / 41,943,040 bytes** are rejected in both handler paths: positive nonzero exit, damaged movie named, zero MRC outputs. Commands, exits and prefix hashes are in `real-prefix-controls.json`; diagnostics are retained alongside it. This input identity differs from the historical 131,245,904-byte report; it is not relabelled as the same artifact.

Modern executable SHA256: `ad5cd5ba40d0ce2e3693bbc027879761d4c32e5220532e5de02f15d9c29ca3fa`.
Compatibility executable SHA256: `5851030d27f6e5f8376eabb6da9b29ac78b34ceccfefdbfc282f8181d7ba9a34`.
Synthetic TIFF SHA256: `95b5f0d37d481355b8abe30f7380c33d9ea173a87bec6e8fc3e567c057622bd4`.

## Allocation and method

CPU64 (`small-refmac-machine`), GCC 13.3.0, CMake 4.4.3, Release, CUDA off. Top-level `taskset -c 32-47 numactl --physcpubind=32-47 --membind=1`, inherited by builds/tests, under `/tmp/motioncorr-issue96-cpu-validation.lock`. Sixteen physical cores on node/socket 1; no SMT. Build parallelism 16, targeted runner cases at most four threads. Logs record affinity and NUMA policy; physical page placement was not separately sampled. Concurrent issue26 CPU work and two unrestricted ctffind processes were observed. These are correctness runs, **not performance measurements**.

`validate.sh` preserves the initial code-revision build recipe; `final-head.txt` records the subsequent exact-revision fetch/checkout, incremental build and rerun after adding the tomography case. `compat-controls.sh` contains the compatibility/harness/prefix recipe. For a fresh reproduction, clone or check out the tested revision into the recipe's checkout location; no build products or tutorial inputs are bundled.

The first compatibility experiment failed to select the legacy branch because later LibTIFF headers restored the version macro. Identical executable/harness hashes exposed this. Its private log is preserved as `compat-controls-unforced.log` on the validation checkout and is excluded from the claimed legacy result. The corrected header shims, compile-time branch assertions, distinct executable hashes and raw final logs establish the reported compatibility-path result.

## Independent source audit

Architecture consultation preceded implementation. A separate read-only audit of the final code/ADR/tests returned `READY_TO_MERGE` for source conditional on final runtime verification, `SPEC_CONFORMANCE_PASSED`, and `LICENSE_COMPLIANCE_PASSED`. No new dependencies, alignment mathematics, kernels or numerical-gate changes. Raw runtime results above satisfy the bounded CPU controls; this is not a merge action.

## Limits

No CUDA execution, grouped-EER runtime case, actual pre-4.5 library, whole-tutorial healthy CPU/CUDA parity sweep, sanitizer race proof or scientific acceptance claim is made here. Existing synthetic regression and TIFF-read suites passed. In-memory TIFF read/seek callbacks have inherited C-ABI/offset limitations and are outside this change. A cleanly terminated shortened TIFF remains indistinguishable from a valid short movie without an authoritative count. STAR counts mean decoded processing frames; EER acquisition counts are not automatically converted to grouped counts. Sparse `?`/`.` integer count cells are not supported by the inherited STAR parser.
