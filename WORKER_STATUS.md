# Worker Status: Issue #92 — TIFF Integrity and Expected-Frame Count Validation

- **Worker / Subagent**: `gemini-3.8-flash-high` via Antigravity harness
- **Task Class**: Correctness & Reliability
- **Assigned Issue**: #92 ("Damaged movie partial-read can pass corrupted/short movie as successful")
- **Base Commit**: `4c952b3f54479653512c4d208e09c9a8c02f3726` (PR #91 merge on `origin/main`)
- **Working Branch**: `round96/92-gemini-3-8-flash`
- **Phase**: Implementation & Validation Complete; Ready for Draft PR

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

- **Local Machine**: Apple Silicon (Darwin ARM64), clang Apple clang 17.0.0, CMake 3.31.5, LibTIFF 4.7.0.
- **Resource Limits**: Local parallelism $\le 8$ cores; zero interference with external processes.
- **NEEDS_GPU**: No GPU required for this task (pure correctness / CPU I/O integrity task).

## Next Steps

1. Create clean git commits on `round96/92-gemini-3-8-flash`.
2. Push branch to `origin`.
3. Open draft pull request with `gh pr create --draft`.
4. Register PR with MCP `link_pull_request`.
5. Post scoped progress comment on GitHub Issue #92.
