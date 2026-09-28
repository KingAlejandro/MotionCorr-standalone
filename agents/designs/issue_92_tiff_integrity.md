# Architectural Design Record: Issue #92 — TIFF Integrity and Expected-Frame Count Validation

- **Issue**: #92
- **Status**: Scoped design
- **Author**: gemini-3.8-flash-high via Antigravity
- **Base Commit**: `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main, Merge PR #91)
- **Branch**: `round96/92-gemini-3-8-flash`

---

## 1. Problem Statement & Failure Analysis

In MotionCorr standalone, TIFF movies are read through LibTIFF via `fImageHandler::openFile` -> `readTIFF` (`src/rwTIFF.h`).

When inspecting the movie dimensions and number of frames (`Image::read(..., select_img=-1)`), `readTIFF` invokes:
```cpp
_nDim = TIFFNumberOfDirectories(ftiff);
TIFFSetDirectory(ftiff, 0);
```

### Root Cause
1. **Silent Truncation during Directory Traversal**:
   LibTIFF's `TIFFNumberOfDirectories(tif)` iterates through the IFD chain calling `TIFFReadDirectory(tif)` until it returns 0.
   - For a **well-formed movie**, the last IFD has `tif_nextdiroff == 0`. `TIFFReadDirectory` returns 0 cleanly without error.
   - For a **truncated movie** (such as the exact 43,748,634-byte prefix of a 131,245,904-byte tutorial movie, or an 8 MiB / 40 MiB prefix), the file is cut mid-stream. IFDs 0..7 are intact, but directory 8 cannot be fetched (`Error fetching directory count` / `Failed to read directory at offset ...`). LibTIFF prints an error message to `stderr` and returns 0.
   - Because MotionCorr never registered a LibTIFF error handler, `TIFFNumberOfDirectories` quietly stops and returns 8.
   - Downstream, `Micrograph` and `MotioncorrRunner` assume the file has 8 frames (`nn = 8`), read frames 0..7 without error, align/sum them, and exit 0 with a success marker, silently discarding two-thirds of the movie without any failure indication.

2. **No Per-Handle Error Boundary**:
   LibTIFF defaults to process-global error reporting via `vfprintf(stderr, ...)`. Errors during directory traversal, tag reading, or strip decoding are printed to stderr but do not interrupt execution unless explicit return codes are checked.

3. **Absence of Expected-Frame Count Verification**:
   Even if an external metadata source (STAR file optics/movies table or CLI parameter) specifies the expected number of frames, MotionCorr never validated the decoded frame count against this expectation.

4. **Undecidable Readable Tail-Loss**:
   If a file is truncated at an exact IFD boundary where `tif_nextdiroff == 0` (or if an acquisition writer crashed immediately after finalizing an IFD), no decoder error occurs. Without authoritative external metadata, such a file is structurally indistinguishable from a legitimate shorter movie. This boundary must be explicitly documented and not conflated with decoder errors or solved by inventing arbitrary defaults.

---

## 2. Technical Architecture & Invariants

### A. Re-entrant LibTIFF Error Capture
- Implement `TiffErrorContext` holding `has_error` and the latest diagnostic (`last_error`); no unbounded error list.
- **LibTIFF >= 4.5+**: Use `TIFFOpenOptionsAlloc()`, `TIFFOpenOptionsSetErrorHandlerExtR()`, and `TIFFOpenExt()` to bind `TiffErrorContext` per handle. This provides re-entrant, thread-safe error capture across concurrent OpenMP threads.
- **LibTIFF < 4.5 compatibility**: Use a `thread_local TiffErrorContext*` pointer with `TIFFSetErrorHandler`, installed once via `std::call_once`. Atomically publish and forward the previous error handler outside an active MotionCorr context. Preserve warning handlers. Modern builds never replace process-global handlers.
- Callbacks must never throw C++ exceptions across the C library ABI boundary; they record the error into `TiffErrorContext` and return. C++ callers check the context immediately after LibTIFF invocations and throw `REPORT_ERROR`.

### B. Directory Traversal and Normal EOF Distinction
- In `readTIFF`:
  - Reset `TiffErrorContext` error flags before directory counting.
  - Call `TIFFNumberOfDirectories(ftiff)`.
  - Check `TiffErrorContext::has_error`. If LibTIFF reported any error (e.g. unreadable IFD offset, truncated directory count, corrupted tags), throw `REPORT_ERROR(name + ": Corrupted TIFF directory structure: " + err_ctx->last_error)`.
  - Check `_nDim <= 0`. If no directories were found, throw `REPORT_ERROR`.
  - When reaching directory EOF cleanly (`tif_nextdiroff == 0`), LibTIFF emits no errors, allowing valid short movies to succeed.

### C. Strip Decoding Integrity
- During `TIFFReadEncodedStrip`:
  - Clear `TiffErrorContext` error flag before read.
  - Validate return code `actually_read` against strip size, row size, and check `TiffErrorContext::has_error`.
  - If LibTIFF reported a read error (e.g. short read, premature EOF in compressed stream, invalid strip offset), throw `REPORT_ERROR`.

### D. Expected Frame Count Contract
- Add optional CLI option `--expected_frames` (default: `-1`, unconstrained).
- Inspect input movie STAR rows for `rlnNrOfFrames` or `rlnTomoTiltMovieFrameCount`. `rlnMicrographFrameNumber` is an index and is explicitly excluded.
- Counts must be positive; CLI accepts only positive values or the `-1` sentinel. Conflicting row count labels are rejected.
- Precedence: row count, then tomography global `rlnTomoTiltMovieFrameCount` mapped through its original optics group, then CLI fallback. Row metadata deliberately overrides a different CLI fallback.
- Expectations describe decoded processing frames, before first/last-frame selection. EER processing frames are already grouped (`raw_frames / eer_grouping`); raw acquisition counts must not be supplied as grouped expectations.
- Resolve once per movie; preserve the vector alongside filenames through unfinished/at-most filtering. Both initial header and execution header use that same resolved count. Resume also compares the saved model's frame count before accepting an existing result.
- If an authoritative expected frame count $N_{exp} > 0$ is available:
  - If $N_{decoded} \neq N_{exp}$, throw:
    `REPORT_ERROR("Movie " + fn_mic + " frame count mismatch: expected " + integerToString(expected) + " frames, but decoded " + integerToString(nn) + " frames.")`
- If no authoritative metadata is available:
  - Do NOT invent a universal 24-frame rule or required default.
  - Rely on structural TIFF integrity (error-free IFD chain ending at normal EOF).
  - Explicitly document undecidable readable tail-loss.

### E. Batch Isolation Composition (PR #91)
- All detected corruptions throw `RelionError` (via `REPORT_ERROR`), caught by the per-movie try/catch in `motioncorr_runner.cpp`.
- Damaged movie is logged and appended to `failed_movies`.
- Healthy movies in the same batch complete normally, write their individual MRC/STAR outputs.
- Joint STAR and PDF outputs are withheld, and process exits with non-zero code.
- Resuming with `--only_do_unfinished` skips completed healthy movies and retries the damaged input.

---

## 3. Changed-File Whitelist

| Path | Role |
| --- | --- |
| `src/rwTIFF.h` | Error handler registration, directory traversal error detection, strip error propagation |
| `src/image.h` | `TiffErrorContext` integration in `fImageHandler::openFile` / `closeFile` / `_read` |
| `src/motioncorr_runner.h` | Member variables for expected frame count |
| `src/motioncorr_runner.cpp` | CLI option `--expected_frames`, STAR metadata inspection, frame count verification |
| `tests/test_damaged_movie.py` | Unit tests for partial truncation (43.7 MB, 8 MB, 40 MB), corrupt directory, invalid offsets, expected count mismatch, valid short controls |
| `agents/designs/issue_92_tiff_integrity.md` | This ADR |
| `WORKER_STATUS.md` | Execution status and coordination tracking |

---

## 4. Test Matrix & Verification Plan

1. **Exact Retained Prefixes**:
   - Tutorial movie 43,748,634-byte prefix (previously decoded 8 frames, exited 0): Must fail, name movie, exit non-zero.
   - Synthetic movie partial truncations (e.g. cut 500,000 bytes leaving 7 of 8 IFDs): Must fail at directory count, name movie.
   - Hard truncations (<= 1 MiB): Continue to fail as before.
2. **Invalid Directory / Strip Offsets**:
   - Corrupted IFD offset pointing beyond EOF or to garbage bytes: Must fail with directory structure error.
   - Corrupted strip offset / truncated strip payload: Must fail during strip decoding.
3. **Authoritative Count Mismatch**:
   - Provide valid 8-frame movie with `--expected_frames 24` or STAR `rlnNrOfFrames 24`: Must fail with count mismatch error.
   - Provide valid 8-frame movie with `--expected_frames 8`: Must succeed.
4. **Positive Controls (Valid Short Movies)**:
   - Valid 2-frame or 8-frame TIFFs with clean EOF: Must succeed with exit 0.
   - Normal directory EOF preserved.
5. **Batch Isolation & Resume**:
   - Damaged-first and damaged-last batch runs at `-j 1` and `-j 4`: Healthy movies retained, job exits non-zero, resume retries damaged.
6. **Numerical Identity on Healthy Inputs**:
   - Healthy movie decoded buffers and corrected MRC outputs must remain identical to baseline.

## 5. PR103 review corrections (Codex, 2026-09-28)

Architecture consultation and independent read-only review cover count semantics, filtering/resume, TIFF callbacks, scope and licensing. No alignment mathematics, CUDA kernels, dependencies or numerical gates change.

Modern TIFF open-option allocation failure is fatal. Error callbacks set the failure flag before best-effort message allocation and never throw; warnings retain LibTIFF's existing behavior. Open-time errors and errors accompanying successful directory selection are also fatal.

Runtime coverage is reported separately for its exact source and executable. The earlier worker's evidence is historical and does not validate these changes. EER grouped-count and in-memory TIFF callback paths are not claimed exercised; inherited in-memory read/seek callbacks can still throw across the C ABI and need separate follow-up. A cleanly terminated shortened TIFF remains indistinguishable from a valid short movie without an authoritative count.
