# Worker Status: Issue #92 — TIFF Integrity and Expected-Frame Count Validation

- **Worker / Subagent**: `gemini-3.8-flash-high` via Antigravity harness
- **Task Class**: Correctness & Reliability
- **Assigned Issue**: #92 ("Damaged movie partial-read can pass corrupted/short movie as successful")
- **Base Commit**: `4c952b3f54479653512c4d208e09c9a8c02f3726` (PR #91 merge on `origin/main`)
- **Head Commit**: `e5907a414fdeb87fa1d72bb733d212771e8e403e`
- **Working Branch**: `round96/92-gemini-3-8-flash`
- **Draft PR**: [#103](https://github.com/KingAlejandro/MotionCorr-standalone/pull/103)
- **Phase**: Complete (Draft PR Opened & Linked; Local and Remote Validation Passed)

## Progress Summary

1. **Root Cause Confirmed**:
   - Analyzed damaged tutorial movie matrix from PR #91. Truncating files after valid IFD directories caused LibTIFF to halt directory enumeration with `TIFFAdvanceDirectory: Error fetching directory count`.
   - MotionCorr silently treated the truncated directory count as a valid shorter movie (e.g. 8 or 7 frames instead of 24 frames), processing partial frame data and exiting 0 with incomplete results.
2. **Re-Entrant LibTIFF Error Intercept Implemented (`src/image.h`, `src/rwTIFF.h`)**:
   - Added `TiffErrorContext` and `TiffErrorScope` with re-entrant error and warning callbacks (`motioncorr_tiff_error_ext_r`, `motioncorr_tiff_warning_ext_r` on LibTIFF 4.5+; thread-local fallback `g_tls_tiff_error_context` on older LibTIFF).
   - Attached `tiff_err_ctx` to `fImageHandler`.
   - In `readTIFF`, verified `err_ctx->has_error` immediately following `TIFFNumberOfDirectories(ftiff)` and frame directory selection `TIFFSetDirectory`. Corrupt directory chains now throw `REPORT_ERROR` with the exact LibTIFF diagnostic.
3. **Expected-Frame Count Validation Implemented (`src/motioncorr_runner.h`, `src/motioncorr_runner.cpp`)**:
   - Added CLI option `--expected_frames <N>` (default `-1`).
   - Parsed per-movie expected frame counts from STAR metadata columns:
     - `EMDL_MICROGRAPH_FRAME_NUMBER` (`_rlnMicrographFrameNumber`)
     - `EMDL_PARTICLE_NR_FRAMES` (`_rlnNrOfFrames`)
     - `EMDL_TOMO_TILT_MOVIE_FRAMECOUNT` (`_rlnTomoTiltMovieFrameCount`)
   - Validated decoded `mic.getNframes()` and `nn` against expected frames, throwing `RelionError` on mismatch, cleanly isolating failed movies while retaining valid outputs.
4. **Comprehensive Test Suite Expanded (`tests/test_damaged_movie.py`)**:
   - Added pure-Python test cases (zero non-standard dependencies; no PIL required):
     1. `test_strip_truncation`: Truncated strip data inside OpenMP fails damaged movie, retains healthy output.
     2. `test_ifd_directory_truncation`: Truncated IFD chain caught during directory traversal with `Corrupted TIFF directory structure` error.
     3. `test_hard_truncation`: 1MB prefix caught cleanly.
     4. `test_corrupt_header`: Zeroed header caught cleanly.
     5. `test_expected_frames_cli`: `--expected_frames 24` on 8-frame movie fails; `--expected_frames 8` succeeds.
     6. `test_expected_frames_star`: STAR metadata `_rlnNrOfFrames 16` on 8-frame movie fails.
     7. `test_positive_control_short_valid_movie`: Valid 4-frame TIFF with clean EOF succeeds without assuming 24 frames.
     8. `test_batch_permutations`: Both `[bad, good]` and `[good, bad]` with `-j 1` and `-j 4` isolate properly.
     9. `test_resume_isolation`: Resuming with `--only_do_unfinished` after replacing damaged movie succeeds and writes joint STAR.
   - All 9 test cases PASSED locally in `ctest -R DamagedMovie` (0.90s).

## Hardware & Environment Witnesses

- **Linux Validation Host (`cpu64` - small-refmac-machine)**:
  - OS: Ubuntu 24.04.2 LTS, Linux 6.8.0-86-generic x86_64
  - Compiler: GCC 13.3.0, CMake 3.28.3, LibTIFF 4.5.1
  - Affinity: `taskset -c 32-47` (Node 1, socket 1, 16 CPUs) under `/tmp/motioncorr-issue96-cpu-validation.lock`
  - Results:
    - `ctest`: **13/13 tests PASSED (100%)** in 8.63s
    - `test_damaged_movie.py`: **9/9 tests PASSED**
  - Binary SHA256:
    - `build/motioncorr`: `b14059884065a0a45e829ba3463199c4f4dd66b5d626ad3944cc1435d5d3580d`
    - `build/runner_numerics`: `a07d7361398ae73247c93798a687d06aa79e867b22376e4bb0e3a08cbf60be5f`
- **macOS Apple Silicon Host (Local)**:
  - OS: Darwin 24.6.0 ARM64, Clang 17.0.0, LibTIFF 4.7.0
  - CTest `DamagedMovie`: **PASSED** in 0.90s
- **GPU Requirements**:
  - `NEEDS_GPU: NO` — Issue #92 is a CPU/file-integrity correctness task.

## Commits & Pull Request

- PR URL: https://github.com/KingAlejandro/MotionCorr-standalone/pull/103
- Linked via `t3-code:link_pull_request` MCP tool.
- Commits:
  - `8cf2b60` docs(design): document TIFF integrity and expected-frame validation (#92)
  - `7c70fea` fix(io): intercept LibTIFF directory errors and validate expected frame counts (#92)
  - `e5907a4` test(io): expand damaged movie and expected frame validation test suite (#92)
