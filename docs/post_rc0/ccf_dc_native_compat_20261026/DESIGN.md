# Native CCF DC conditioning for CPU/CUDA compatibility (research prototype)

Status: default-off research code on C1 `b305b23b` (non-docs tree identical to the tested production commit `e77a51a2`; `git diff e77a51a2 b305b23b -- . ':!docs'` is empty). Not a candidate for merge, default, gate, policy or release. Native movie campaign is HELD until independent source review and a parent-frozen matrix (see CONTROL_PLAN.md).

Motivation (PR288, `58cd3a56`): on C1 the CPU and CUDA inverse CCF differ at about 0.0097 px for identical valid spectra; zeroing only the CCF spectrum DC bin on both sides cuts that to 4.6e-6 px (~2113x) with no integer peak change. That is a numerical-conditioning diagnosis, not a statement about physical motion. This prototype makes the same operation available inside the product so CPU and CUDA can be compared end to end.

## Operation

With `-DMC_EXPERIMENT_CCF_DC=ON` and `MC_EXPERIMENT_CCF_DC_ARM=none|global|local|both`, the (0,0) bin of the disposable CCF scratch spectrum is set to zero immediately before the CCF inverse transform. In exact arithmetic this subtracts a constant from the map. Frame and resident spectra, weights, peak search, ties, guard, fit, convergence, acceptance, reconstruction and the published movie DC are untouched. No time/reference/peak/stopping/fit/weighting change, no coupled peak (the falsified H7 package is not ported), no isotropic or B2 option.

Hook sites (all CCF inverses; DW, reconstruction and movie-session C2R sites are not CCF and are untouched):

| Site | Code | Stage semantics |
|---|---|---|
| CPU | `MotioncorrRunner::alignPatch`, before `NewFFT::inverseFourierTransform(Fccs[tid], ...)` | `is_global` argument |
| CUDA single | `cudaAlignPatchDeviceWithWorkspace`, before `projectHermitianColumns` | `is_global`: global, and local per-patch/retry (resident and windowed) |
| CUDA batched | `cudaAlignPatchBatchDevice` | local only (`false`) |

The primitive is the reviewed #262/PR284 one (`3eee0a4b`, GPL notices kept). Differences from it:

1. Unset arm means `none` (PR284 aborted at the first CCF).
2. `experimentCcfDcCheckRequest()` runs once at the end of `MotioncorrRunner::read()` in every build, before any device query or pixel work. It refuses: an unknown or empty arm; an arm, `MC_EXPERIMENT_CCF_DC_REPORT` or `MC_DIAG_MODEL_OUT` in a build without the hooks; an arm or tap on `--use_motioncor2`; a report or tap path that already exists; an empty report/tap path. A request is never ignored. After the movie list is final, still before the first movie, `initialise()` refuses a tap with other than one movie and creates the tap file exclusively, so an unwritable tap path is refused before any pixel work.
3. The witness is JSON written to `MC_EXPERIMENT_CCF_DC_REPORT` (created exclusively at start with status `incomplete`, rewritten with status `atexit` by the exit handler; `atexit` says the handler ran, not that the producer succeeded, so each producer's own exit status is retained separately; a missing or `incomplete` witness marks an abnormal end): per site (`cpu`, `cuda_single`, `cuda_batched`) and stage, `calls_eligible/zeroed` and `frames_eligible/zeroed`. Nothing is added to the console or product logs.
4. Default path: no hook code is compiled. The only default-build additions are the request check (env reads only, can only refuse) and one include. Arithmetic, metadata, publication and exit status are unchanged for runs without these variables.

## Runtime-field tap

The reviewed #269 `capture_runtime_model` block (`MC_DIAG_MODEL_OUT`) is reused verbatim, behind the same build option: after local fitting and before the STAR writer it writes the runtime global shifts (`xshifts*prescaling`), the 18+18 polynomial coefficients and `local_enabled` as JSON. It reads no truth, changes no computation, and is read by the unchanged `tools/check_realistic_motion.py`. Added here only: the file is created exclusively with an `incomplete` placeholder before the first movie (the block then rewrites it) and the one-movie rule. A crashed or failed run leaves the placeholder, which has no `global` key. Convergence and per-patch acceptance are not in the tap; they come from the existing product log through the unchanged checker's log parser, and the witness counters are reported separately. Real STAR output is scored separately from the tap.

## Test-only isotropic global weight (compile-gated)

Needed because the retained harmful control `vel1-N20-iso` has no route on C1. `-DMC_TEST_ONLY_ISOTROPIC_GLOBAL_WEIGHT=ON` (requires the experiment option; default OFF; CMake prints a warning) replaces `nfx` by `pnx` in the x normalisation of the CCF B-factor weight, global stage only: CPU `alignPatch` (`weight_x_norm`) and CUDA `computeWeightsKernel` argument at the `cudaAlignPatchDeviceWithWorkspace` call, with `is_global` added to the CUDA workspace key in that build. It is a compile-time constant: no CLI flag, no environment switch, local stage and batched path unchanged, default build code unchanged (`nfx` is passed as before). Binary identity: its own build directory and hash, the CMake warning, and `test_only_isotropic_global_weight: true` in every witness. It exists solely for the retained N controls and is never used for the native movie tier.

## Tests

- `ExperimentCcfDcStage` (PR284 oracle, unchanged gates G1-G5, ported to C1): counters select exactly the requested stage at every site; a selected stage is bit-identical across spectrum-DC pedestals; independent long-double same-CCF reference (error <= 1e-3 px where the reference margin is >= 1e-4 of contrast); resident spectra (incl. every frame's DC bin) unchanged; power-of-two amplitude scaling exact; none is the unconditioned path. Six restoring mutants (`ExperimentCcfDcStageMutant_*`: CPU restore / wrong bin / stage swap; CUDA single restore / batched restore / resident bin / single stage swap) must be rejected. CPU paths run in a CPU build; CUDA paths need a GPU.
- `CcfDcRequest` (new, every build): refusals above; `none` equals unset (pixels and console); witness counts select exactly the requested stage on a CPU run; tap schema, exclusivity and one-movie rule. A default-build run of the experiment mode, the reverse, and an isotropic binary run as non-isotropic all fail (negative controls run locally). `ExperimentCcfDcStage` also carries gate G6 in the isotropic build: the isotropic and production references differ by more than 1e-3 px (detection power), and one CUDA workspace reused global then local equals fresh workspaces; extra mutants `cpu/cuda_iso_wrong_norm`, `cpu/cuda_iso_leaks_local`, `cuda_iso_key_ignores_stage` must be rejected.

## Limits

No accuracy, parity or performance claim is made by the prototype or its unit tests. CPU and CUDA hooks are separate sites; "CPU-on" and "CUDA-on" mean the same declared operation, not bit equality. CUDA hook behaviour on silicon is UNRUN until the native build and oracle have run on the venue.
