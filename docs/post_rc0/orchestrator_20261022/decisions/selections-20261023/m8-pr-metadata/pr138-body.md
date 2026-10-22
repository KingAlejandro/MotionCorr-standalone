**Parked — maintainer M8 selection, 23 October 2026 (Europe/London).**

This PR remains open at retained head [`875857f1ba3390c53cdf97f68afaa2a1f1e4832b`](https://github.com/KingAlejandro/MotionCorr-standalone/commit/875857f1ba3390c53cdf97f68afaa2a1f1e4832b). Historical nvCOMP widening evidence is retained. This stack stays outside C1; existing D1/T1 dispositions are unchanged, and no format widening is adopted. No branch deletion or history rewrite is authorized.

The original PR description is retained below.

---

Stacked on #137 (compact native ingest for unsigned 8-bit TIFF); review that first — the diff here is only the nvCOMP widening.

## Result

The nvCOMP Deflate fast path admitted exactly one encoding: 16-bit samples, one
full row per strip. Both restrictions were in the staging arithmetic, not in
anything the decoder requires — a TIFF strip is one independent Deflate stream
whatever its row count, so it is one nvCOMP chunk either way.

It now admits 8- or 16-bit unsigned samples and any `RowsPerStrip`, including a
short final strip. Measured per-movie, against `main`:

| input | route change | per-movie wall | host RSS |
|---|---|---|---|
| uint8 Deflate, 1 row/strip | float → nvcomp | 0.811 → 0.452 s (−44%) | 1561 → 486 MiB |
| uint8 Deflate, 16 rows/strip | float → nvcomp | 0.930 → 0.462 s (−50%) | 1557 → 464 MiB |
| uint8 Deflate, 48 frames | float → nvcomp | 1.736 → 0.693 s (−60%) | 2865 → 671 MiB |
| uint16 Deflate, 2 rows/strip | compact → nvcomp | 0.806 → 0.449 s (−44%) | 906 → 533 MiB |
| uint16 Deflate, 8 rows/strip | compact → nvcomp | 0.810 → 0.471 s (−42%) | 907 → 546 MiB |
| uint16 Deflate, 512 rows/strip | compact → nvcomp | 0.783 → 0.583 s (−26%) | 928 → 526 MiB |

Five unchanged-route variants span −4.0% to +0.9% on the same metric; that is
the noise floor.

## Trust boundary — please read before approving

This change **moves inputs onto the nvCOMP decoder that previously went through
LibTIFF**: 8-bit Deflate TIFFs, and Deflate TIFFs with more than one row per
strip. The checks applied to them are exactly the ones `main` already applies
to 16-bit one-row-per-strip input — positive encoding enumeration, zlib wrapper
validation before submission, per-chunk status, per-chunk decoded length and a
device-side Adler-32 recomputation — so nothing is weakened relative to the
released fast path. But NVIDIA documents corrupt input to
`nvcompBatchedDeflateDecompressAsync` as undefined behaviour with limited
validation, and the population of files reaching that decoder is now larger.

That is a policy decision, not a correctness one, and it is why this is
separate from the compact widening, which moves nothing onto the GPU decoder.
`docs/input_backends/FAILURE_POLICY.md` states the per-category contract and
the options (#134). A deployment that does not accept the boundary can set
`--ingest compact` and still avoid the host float movie.

## How the geometry is made checkable

The strip count, the short final strip, the per-chunk declared length and the
row addressing moved out of the ingest function into a `StripGeometry` in
`cuda_deflate_layout.h`, called by both the host planner and the ingest kernel.
None of those is observable without a GPU and a pixel comparison: a full-length
final strip or padding between rows inside a strip decodes, reports success,
and is wrong only in part of every frame.

`tests/test_deflate_layout.cpp` exercises it across sample widths,
`RowsPerStrip` 1/2/4/7/8/whole-frame, four output alignments and a height no
tested `RowsPerStrip` divides, and asserts that `RowsPerStrip == 1` reproduces
the released row-pitch addressing exactly. **Three compiled mutants of the
production arithmetic each turn it red** — full-length final strip (27 checks),
unaligned strip slots (18), padded rows inside a strip (56).

One defect this found that the device could not have: `frameStageBytes` sized
the compressed staging by walking `ny` entries of a per-strip vector. With one
row per strip those are the same number; with any larger `RowsPerStrip` it read
past the vector, and the nonsense size made every multi-row movie decline the
fast path on the pinned budget — a silent fallback with correct products.

## Evidence

As for the parent PR — 26 of 26 complete-output-tree comparisons PASS, with an
exact copy passing and one changed pixel of 85,433,880 turning the same
comparison red — plus:

**Host-to-device bytes** (Nsight, contention-immune), one movie per arm:

| input | main | branch | reduction |
|---|---|---|---|
| uint8 Deflate, 24 frames | 1,434.807 MB | 162.985 MB | −89% |
| uint8 Deflate, 48 frames | 2,801.773 MB | 258.129 MB | −91% |
| uint16 Deflate, 8 rows/strip | 751.336 MB | 191.968 MB | −74% |
| three unchanged-route variants | — | — | byte-identical |

Paired process wall over nine repeats on six movies, arm order alternating:
uint8 Deflate **8.63 → 4.49 s, 8/8 pairs**; uint16 Deflate 8 rows/strip
**7.05 → 4.69 s, 7/7**; the unchanged-route null control at **−0.00 s, 4/8**.

Also: the existing in-tree nvCOMP failure controls
(`CudaNvcompReconstructionFailures`, `CudaPreprocessingFailurePaths`) pass
unchanged with the widened gate, and `--ingest nvcomp|compact|float` pinning is
exercised per variant so the route matrix is about eligibility rather than
defaults. `docs/input_backends/RESULTS.md` carries the full tables and the
limitations.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
