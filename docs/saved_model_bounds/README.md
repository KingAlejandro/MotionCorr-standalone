# Saved motion-model bounds (issue #67)

`Micrograph::read()` previously assigned saved global shifts with unchecked
1-based indices. Frame 0 produces an AddressSanitizer heap buffer overflow on
main `6c87441d3e44e977994bd26175601092cc344a21`. `getShiftAt()` also indexed before
checking its argument and tested X twice, accepting a Y-only NOT_OBSERVED value.

The change validates positive dimensions, integer narrowing and index-size
arithmetic; start-frame range; global-shift range, uniqueness and finiteness;
and hot-pixel bounds before conversion. Saved integer fields are read as `long`
before narrowing, so e.g. 4294967300 cannot wrap into dimension 4. The local
model remains owned by a `unique_ptr` until all tables are accepted, including
when construction throws. Public in-memory hot-pixel vectors are checked again
before mask allocation/assignment.

Sparse nonempty global-shift tables remain supported. Missing frames are
NOT_OBSERVED; either missing axis returns status -1 and the nearest preceding
fully observed pair, or zero if none exists. Finite fractional queries in
[1, n_frames] preserve the existing global-index truncation and continuous local
polynomial evaluation. Finite in-bounds fractional hot-pixel coordinates keep
their previous conversion to integer pixels. No kernel, FFT, RNG, motion
estimation, output format or numerical tolerance changes.

This is a parser/query bounds repair, not the configuration-bound resume receipt
work in #142. Resume's existing completion helper catches the new parser errors
and reprocesses invalid saved models. General memory admission for large but
representable dimensions, arbitrary malformed-STAR grammar and external-engine
compatibility are separate contracts. The unknown-local-model policy is unchanged.

## Executed validation

Linux x86-64, GCC 13.3, CMake 3.28.3, Python 3.12.14, FFTW 3.3.10, LibTIFF 4.5.1,
CPU Release build. Required collection **34/34**; CTest **34 passed, 0 failed,
0 skipped**. `MicrographModelBounds` checks 38 malformed saved models, nine
invalid frame queries, sparse/Y-only/fractional/round-trip and mask controls.
Its real CLI resume checks three invalid hot-pixel completion records, exact
reprocessed per-movie STAR, corrected-image payload and joint STAR (only the
declared output-prefix replacement), plus untouched valid product bytes/mtimes.
The regression passes normally and under Python `-O`.

Targeted ASan/UBSan instrumentation of the actual `micrograph_model.cpp` also
passes the regression. Other linked core objects are the Release build.
LeakSanitizer cannot inspect `/proc` tasks here, so runs use
`ASAN_OPTIONS=detect_leaks=0`; **leak detection is unrun**. Production cleanup is
covered by the RAII ownership structure, not claimed as a measured leak result.

Actual predecessor controls discriminate the frame-0 parser/query overflows,
Y-only typo, duplicate rows, hot-pixel bounds and dimension narrowing. The
baseline CLI incorrectly resumes the corrupt hot-pixel record; the candidate
repairs it. Nonfinite literal rejection already existed in MetaDataTable and
is retained as coverage, not attributed to this patch.

Reproduce the new regression after a standard CPU build:

```sh
python3 tools/validate_test_collection.py --test-dir build --min-count 34
ctest --test-dir build --output-on-failure --parallel 2
python3 -O tests/test_micrograph_model_bounds.py --binary build/motioncorr --helper build/runner_numerics
```

[Validation and source hashes](validation.json),
[control build commands](control-build.json), [parser controls](negative-controls.json),
[query overflow](query-negative-baseline.log), [resume control](resume-negative.json).
Control binaries reuse the current test adapter and replace only the production
model object with the pinned predecessor or sanitizer-instrumented source.
Native CUDA compilation/execution, GPU performance and downstream scientific
acceptance are unrun; this CPU evidence does not establish those claims.
