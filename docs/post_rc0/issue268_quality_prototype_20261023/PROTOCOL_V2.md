# #268 quality-report prototype — protocol v2 (hardening, frozen 23 Oct 2026)

Frozen before any build or run of v2 source. Design: `DESIGN_V2.md`. The v1
protocol and its `c347f59f` evidence are unchanged and do not transfer to v2.
Every row is UNRUN until a retained record shows otherwise. A failure is kept as
FAIL; there are no in-place reruns under the same evidence identity. If a row
must be repeated after a fix, it gets a new source SHA and a new evidence
directory.

## Binaries

| Id | Source | CMake | Use |
| --- | --- | --- | --- |
| V0 | C1 base `bbf24607` | default | reference |
| V1 | v2 head | default (option OFF) | neutrality, full CPU CTest |
| V2 | v2 head | option ON | report runs, full CPU CTest |
| V3/V4 | v2 head | `-DCUDA=ON`, option OFF / ON | compile only (`--target motioncorr`), never executed; only if the shared build lock is free |

Fixtures: `generate_motion_diagnostics.py` output that must equal
`GENERATION_RECORD.json` byte-for-byte. Common argv and comparison rule as in v1
(`PROTOCOL.md`), plus: per-movie logs must be equal after removing the
`Full movie wall time:` line; no `*.tmp.*` file may remain in any output tree.

## Campaign (at most 16 MotionCorr invocations; CTest invocations counted separately)

| Q | Bin | Input, patches | Extra | Expected |
| --- | --- | --- | --- | --- |
| Q1 | V0 | batch6, 3×3 | — | reference |
| Q2 | V1 | batch6, 3×3 | — | products and logs equal Q1 |
| Q3 | V2 | batch6, 3×3 | — | products and logs equal Q1; no quality file |
| Q4 | V2 | batch6, 3×3 | flag | products and logs equal Q1; all v1 E2 sidecar checks plus the strengthened checks below; summary complete |
| Q5 | V0 | `in/zero.mrcs` twice, `in/affine.mrcs`, `in/affine.mrc` (integer content), 3×3 | — | collision reference |
| Q6 | V2 | same | flag | products/logs/exit equal Q5; summary has 4 entries in membership order (joint STAR rows = 4); all four `output_root_collision: true`, `publication: ambiguous_output_root`, no sidecar; no `zero`/`affine` sidecar file; evidence incomplete |
| Q7 | V0 | `in/zero<0xE9>.mrcs` (zero content), `in/z<U+00E9>ro.mrcs` (integer content), 1×1 | — | encoding reference |
| Q8 | V2 | same | flag | products/exit equal Q7. If Q7 exits 0: both sidecars and the summary decode as strict UTF-8 JSON; the non-UTF-8 movie path is `{"non_utf8_bytes_hex": …}` whose bytes equal the file name; the UTF-8 path is the plain string |
| Q9 | V2 | prepared resume tree from Q4 copies, `--only_do_unfinished` | flag | exit 0, nothing reprocessed; zero (global state `BOGUS`), integer (`motion_identifiability: identifiable`), fractional (global block removed), affine (`movie.bytes` as a string), noisy (`peak_validity: valid`) → `unknown_legacy`/`sidecar_invalid`; flat unchanged → `resumed_sidecar` |
| Q10 | V0 | same tree without sidecars, `--only_do_unfinished` | — | joint STAR equals Q9's |
| Q11 | V0 | zero+integer, 1×1, `integer.mrc` pre-created as a directory | — | write-failure reference |
| Q12 | V2 | same | flag | exit equals Q11 (non-zero); integer `failed`/`product_write_failed`; summary `withheld_movie_failures` |
| Q13 | V2 | batch6, 3×3, `flat.quality.json` pre-created as a directory | flag | products/exit equal Q1; summary records the flat sidecar write failure |
| Q14 | V0 | integer, 3×3, `--max_iter 1` | — | reference |
| Q15 | V2 | same | flag | products equal Q14; `global_only`/`too_few_converged_observations`, `min_observations_exclusive` 18 (bound), fit and distortion limits null |
| Q16 | V1 | batch6, 3×3 | flag | superseded by amendment A1 (originally: non-zero exit, no products) |

## Amendment A1 (23 October 2026, before any remote run of v2)

The first local development run of the v2 harness on `1215febd`
(`/tmp/q268v2-dev1`, macOS, encoding pair skipped) showed that Q16's frozen
expectation was wrong: the parser only warns about unknown options, so the OFF
build exits 0 and processes the batch. The same run's checker crashed on a
negative-control directory name collision before writing results. Q16's
expectation is replaced, prospectively for the remote campaign only:

Q16. Exit 0; stderr contains `Option --experimental_quality_report` and
`is not a valid RELION argument`; products and logs equal Q1; no quality file.

The same development run showed that log comparison must also ignore error
backtrace frames and the `in: <source file>, line N` line, which name the binary
or source checkout and carry addresses (they differ between V0 and V2 builds in
the failure runs Q11/Q12). The log rule is therefore: equal after removing
`Full movie wall time:` lines, `in: …, line N` lines and backtrace frame lines.
On macOS `/proc/self/exe` is absent, so `binary_sha256` is `unavailable` and
the identity checks only pass on Linux.

## Strengthened checker (applies to every V2 report run)

Identity: `binary_sha256` equals V2's hash; `configured_source_revision` equals
the v2 head and `dirty` false; `argv` equals the recorded run argv. Summary:
each entry's sidecar SHA-256 equals the file; counts equal the entries.
Sidecar: `solver_attempts` = sum of attempts; `patches_recorded` = number of
patch records; `converged + dropped + interrupted = patches_recorded`;
per-patch route `cpu`, kind `first`; global route `cpu`; `max_iter` equals the
argv value; `observations` = 5 × converged patches; `fit_rmsd_x/y` equal the
log's `Polynomial fit RMSD` line when present; `movie.bytes` equals the input
size; publication/model/STAR consistency as in v1.

Negative controls (copies of Q4/Q6/Q8/Q9 outputs; each must be rejected):
identity binary hash, argv, summary sidecar SHA-256, summary count,
`solver_attempts`, a per-patch `final` relabel with consistent counts,
`observations`, `fit_rmsd_x`, `movie.bytes`, a collision entry relabelled
`published`, an encoded path whose hex differs, and a resume entry relabelled
`resumed_sidecar`. Positive control: the untouched copy is accepted.

## Unit controls (C++, no MotionCorr process; CTest `QualityReportUnit`, ON builds only)

U1 interrupted patch → `interrupted`, counts exclude it from `dropped`, local
state `interrupted`. U2 ill-formed UTF-8 → hex object, well-formed preserved,
output is well-formed UTF-8. U3 resume: each F2 violation (including a `/0`
schema, a missing state, a wrong reason) → `sidecar_invalid`; binding mismatch
→ `sidecar_stale`; untouched → `resumed_sidecar`. U4 unknown values → null.

## CTest

Full CPU CTest of V1 and V2 on 4GPUs (cores 14–15, `-j1`). Record collected
and passed counts and failures; V2 must collect V1's tests plus exactly
`QualityReportCheckerSelftest` and `QualityReportUnit`. A failing existing test
is retained and reported, not retried.

## UNRUN by design

All CUDA execution; native trigger for an interrupted patch (unit control only);
summary write failure (code path unchanged except encoding); distortion-guard
and fit-RMSD fallback reasons; dataset/multi-GPU, tomography, timing.

## Resources

4GPUs CPU 14–15 only, fresh scratch under `/mnt/clathrin` (cap 8 GiB),
`OMP_NUM_THREADS=1`, `--j 1`, builds `-j2` under nonblocking
`/tmp/motioncorr-build.lock` plus a private 14–15 lease. Admission: fresh
occupancy, guard and old q268 processes absent, locks unheld. No SSH retry on
refusal, no GPU, no `nvidia-smi`, no write to old evidence or products.
