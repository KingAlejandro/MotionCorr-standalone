# Preprocessing failure disposal — 29 September 2026

Implementation and tests: `1d533d214c5cbda3114539cee950e9524c62bffd`, source tree
`9467eb34d5192dbb4fbe645254452f36f4064d8b`. This extends PR118's existing PR115 composition.

A consumed fatal sparse-update error previously disappeared when the runner destroyed the
session, allowing host materialization and another CUDA FFT. Float gain/sum had the same gap.
A recoverable operation could also encounter a fatal error during session cleanup, after the
runner's previous health check. The new disposal helper explicitly releases resources, checks
preserved plus pending fatal state while the object still exists, and permits reset/recovery
only when neither source establishes poisoning. Initialization, gain/sum, sparse preparation or
update, and forward-FFT fallback use the same helper.

## Native evidence

- VM GPU0: `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`; CPU mask `96-103`,
  build `-j4`, runtime `--j 4 --max_io_threads 2`; Release CUDA12.8 `sm80`.
- Held `/tmp/motioncorr-gpu0-correctness.lock`; builds additionally serialized through
  `/tmp/motioncorr-vm-build.lock`. GPU0 was empty before/after; unrelated devices/processes
  were untouched. No memory binding or physical-core equivalence is claimed.
- Exact test binary SHA256:
  `b10ef25e4081fef9948c5aaeb4f609456ceab86e86c60c77a1c88006cf41085e`.
- Mutant SHA256: `8257d110d66219750da327a8b3facca4447bb1f03c5ede3ff527655002a90743`.
- Deterministic 48×40×6 TIFFs: U16
  `638205aea8d5dfbac69736fca7fd511f59682af5e33a5bd7ec8a9e8470c201f8`, float
  `c60c0f5356692343e63690f5470205cf2902c3adf5c57f94031473e4a350fe95`;
  input STAR `6768eaeeb2948c952ce822397df3e6c870bd0b3774335aa4b94266c985dfc87a`;
  explicit one-pixel defect rectangle prevents an empty sparse-update case.
- Both healthy fixtures pass. Recoverable sparse-update allocation failure materializes
  the host frames and produces identical complete MRC/full normalized header/STAR products.
- Fatal initialization, sparse update, float gain/sum, forward FFT, and recoverable sparse
  update followed by fatal cleanup all exit nonzero, publish no image/STAR, and perform no
  subsequent allocation redispatch or U16 host materialization. Operation and fatal-cleanup
  attribution are both retained. All cases report zero owned allocations/stale releases.
- Three controls with only the disposal refusal disabled complete normally and redispatch
  CUDA after the injected fatal sparse, cleanup, or float-gain error. Their complete products
  equal the healthy outputs. Thus unrelated mutant crashes cannot satisfy the controls.
- Native CTest **25/25**, including `CudaPreprocessingFailurePaths`, `CudaFaultMatrix`,
  `CudaU16StagingEquivalence`, `CudaWrapperUploadFailure`; comparator tests **16/16**.

Commands and payload PID/start/executable/cpuset/initial NUMA-map records are retained under
`/home/alex/mc118-preprocess-20260929T1311` and the coordinator's matching `work/` directory.
The evidence archive SHA256 is
`472e0190e26677b4461a8c7473c8ab9504957b9a20ae95cec92550ff7f9ae9ed`.
Reproduce with the registered CTest or:

```sh
python tests/run_preprocessing_failure_controls.py --binary build/motioncorr_faultinject \
  --mutant-binary mutant.motioncorr_faultinject --workdir NEW_DIRECTORY
```

The initial archive-only CTest run was **24/25**: its invalid-Git-ref diagnostic differed from
the test's Git-checkout expectation. That failed run remains retained. Adding the exact commit's
Git metadata changed no tracked file or binary, and the complete rerun passed25/25. An initial
local comparator invocation lacked NumPy; the native host's configured NumPy interpreter passed.

These are injected status codes at real production helper/runtime boundaries, not real GPU
poisoning. No performance measurement, full24 rerun, or default-promotion claim follows. The
current no-gain RSS increase documented in RESULTS remains unresolved.
