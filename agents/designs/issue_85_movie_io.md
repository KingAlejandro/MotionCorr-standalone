# Architectural Design Specification: Movie I/O and gain-sum optimization

- Issue: #85
- Status: Approved narrow design; implementation awaiting execution evidence
- Architect: independent Sol reviewer, consulted before implementation
- Base: `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26`

## Scope and contracts

Carry the ordered tiled gain-and-sum loop, TIFF directory counting and row flip, direct matching-type MRC writes, timing labels, and gain cache. Include header-only TIFF allocation removal. Check per-frame directory selection; invalidate cache before refill and publish a validated entry only.

Separate independent PRs isolate performance work (#85) from damaged-input handling (#86). No prefetching, new CLI options, CUDA allocation changes, threshold changes or numerical algorithm changes. Existing upstream fixtures are retained; this package adds no tests and runs no builds or tests.

## Numerical and resource constraints

Healthy pixels must remain exact within the same backend. Headers must match with the existing timestamp normalization and STAR metadata must match under documented normalization. Frame-order floating point accumulation remains unchanged. CPU and CUDA agreement is a separate question; no historical CPU/RELION Gate 2 pass is claimed. No new movie buffers or device allocations. Gain is const at use sites and a failed refill must leave the cache invalid.

## Acceptance and outstanding evidence

Independent static review checks scope, concurrency, resource lifetime and preserved GPL notices. Final independent heads need fresh ordered decoded-pixel, corrected-pixel, header and STAR evidence; older combined-branch results are reported evidence only. Damaged-plus-healthy processing, missing/corrupt headers, resumed success markers, damaged-movie retry and nonzero job failure need execution evidence for the final correctness head. Timing must be pinned to exact source, binary, command, allocation and repeated end-to-end measurements. No runtime verification is performed during this packaging task.

## License

Existing RELION GPL-2.0-or-later notices are preserved. No dependency or third-party code is added.

## Changed-file whitelist

- `CMakeLists.txt`
- `src/motioncorr_runner.cpp`
- `src/motioncorr_runner.h`
- `src/rwMRC.h`
- `src/rwTIFF.h`
- `tests/test_gain_cache.py`
- `tests/test_runner_numerics.cpp`
- `tests/test_tiff_read.py`
- `agents/designs/issue_85_movie_io.md`
