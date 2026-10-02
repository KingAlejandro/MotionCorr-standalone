# Input-route failure and trust policy (issue #134)

Scope: the three movie ingest routes a CUDA build can take for a TIFF, and what
each one does with input that is unsupported, malformed or resource-starved.
This is a statement of what the code at this branch head does, derived from the
source and from the controls listed at the end. It is not a safety proof for the
nvCOMP decoder.

## The three routes

| route | decoder | selected when |
|---|---|---|
| `nvcomp` | nvCOMP batched Deflate, on the device | resident CUDA session, non-EER TIFF, and the positively enumerated encoding below |
| `compact` | LibTIFF, on the host, into native-sample host staging | resident CUDA session, non-EER TIFF, `UChar` or `UShort` sample type |
| `float` | LibTIFF, on the host, into a float movie | everything else |

`--ingest {auto,nvcomp,compact,float}` pins the route; anything but `auto` fails
a movie that cannot take the named route rather than silently using another.
`--ingest_witness <file>` records the route each movie actually took.

The nvCOMP encoding is enumerated positively — every tag the path does not
implement is a refusal, not a default:

* `SAMPLEFORMAT_UINT`, 8 or 16 bits per sample, 1 sample per pixel;
* `PREDICTOR_NONE`; `FILLORDER_MSB2LSB`; `PLANARCONFIG_CONTIG`;
* native byte order; Deflate or Adobe-Deflate compression;
* frame geometry equal to the session's, which is also what excludes IMOD's
  packed 4-bit K2/K3 format (rwTIFF doubles its logical width);
* any `RowsPerStrip`, with the strip count and strip sizes checked against
  `RowsPerStrip x width x sample width` and `TIFFVStripSize` for the final strip;
* `RowsPerStrip` and sample width identical across the movie's directories.

## Category table

| category | detected | where | consequence |
|---|---|---|---|
| valid but unsupported encoding | before any decode | nvCOMP eligibility gate, tag reads only | named decline in the log, delegate to `compact`, else `float` |
| valid encoding, no resident session | before any decode | route selection | delegate to `float` |
| truncated / corrupt IFD chain | at header read | `rwTIFF` intercepts LibTIFF errors around `TIFFNumberOfDirectories` | movie fails; route-independent |
| short movie vs declared frame count | at header read | `--expected_frames` / per-movie STAR row count | movie fails; route-independent |
| unreadable raw strip | before submission | `TIFFReadRawStrip` short read | batch refused, delegate to the host reader |
| invalid zlib wrapper (CM, CINFO, FCHECK, FDICT, length < 7) | before submission | `zlibWrapperIsUsable` on the staged bytes | named decline in the log, delegate to the host reader |
| structurally corrupt Deflate payload | **not** detected before submission | — | submitted to nvCOMP; see the trust boundary below |
| wrong decoded length | after decode | per-chunk `h_act_size[c] != h_dec_size[c]`, per chunk, following the short final strip | batch refused, delegate to the host reader |
| decoder-reported chunk failure | after decode | per-chunk `nvcompStatus_t` | batch refused, delegate to the host reader |
| valid stream, wrong Adler-32 trailer | after decode | Adler-32 recomputed on the device over each decompressed strip and compared to the stored trailer | batch refused, delegate to the host reader |
| pinned-memory budget exceeded | before allocation | `pinnedReserveBytes` against `MOTIONCORR_NVCOMP_PINNED_MAX_MB`, on the bytes actually pinned | decline, delegate to the host reader |
| device scratch too small for a one-frame batch | before allocation | arena fit loop | decline, delegate to the host reader |
| recoverable device-ingest failure | at the call | `MovieIngestStatus::RecoverableFailure` | live session retained; `auto` re-reads the immutable movie through the eligible host route and fully overwrites raw frames and sum; pinned `nvcomp` fails the movie |
| fatal device/context failure | at the call | `MovieIngestStatus::FatalDeviceFailure` / `cudaRetryDecisionFor` | run fails; **no** CPU fallback and no re-dispatch |

Host-route delegation in the table applies to `--ingest auto`. With
`--ingest nvcomp`, a decline or recoverable ingest failure refuses the movie
before a host re-read because the requested route did not succeed. Under `auto`,
the successful host re-read's gain/sum preprocessing overwrites the retained
session's `d_Iframes` and `d_Isum` in full before they can be consumed.

Nothing downstream consumes a batch that failed any post-decode check: the
status, length and Adler-32 loops all run before the conversion kernel for that
batch is launched, and a refusal returns before it.
The Adler kernel itself reads a chunk's output only after its decoder status and
actual size are accepted; the complete host status/length pass precedes checksum
diagnostics. The bounded modular arithmetic and scoped controls are documented in
[`CHECKSUM_REPAIR.md`](CHECKSUM_REPAIR.md); prepared native controls remain unrun
by the repair owner.

## Trust boundary

NVIDIA documents `nvcompBatchedDeflateDecompressAsync` as performing limited
validation, with corrupt input producing undefined behaviour and error reporting
not guaranteed. Every check above is therefore an **output-integrity** check,
not a proof that malformed compressed input was safe to execute inside the
decoder. The zlib wrapper check is the only pre-submission filter, and it reads
two header bytes — it rejects a stream that is not Deflate at all, and nothing
about a stream whose body is corrupt.

What this branch changes about that boundary:

* **`compact` widened to uint8 (default on).** This moves 8-bit TIFFs from the
  float host reader to the compact host reader. Both are LibTIFF; the codec,
  its validation and its failure behaviour are identical, and only the
  destination sample type differs. No input moves onto the GPU decoder and the
  trust boundary does not move.
* **`nvcomp` widened to uint8 samples and arbitrary `RowsPerStrip`.** This does
  move inputs — 8-bit Deflate TIFFs, and Deflate TIFFs with more than one row
  per strip — from LibTIFF onto the nvCOMP decoder. The checks applied to them
  are exactly the ones main already applies to 16-bit one-row-per-strip input,
  so nothing is weakened relative to the released fast path, but the population
  of files reaching a decoder with documented undefined behaviour on malformed
  input is larger. That is a policy decision, not a correctness one, which is
  why it is a separate change from the compact widening.

A deployment that does not accept the nvCOMP trust boundary can set
`--ingest compact`, which keeps every TIFF on LibTIFF while still avoiding the
host float movie.

## What the controls here do and do not establish

`tests/test_deflate_layout.cpp` establishes the staging and strip arithmetic
without a device, including against compiled mutants of the production
geometry. `docs/input_backends/harness/` establishes that the samples the
compact route stages equal an independent decode, every sample, with mutation
controls. The campaign in `RESULTS.md` establishes product identity across
routes on real movies.

None of those is evidence about malformed-input memory safety inside nvCOMP.
No fault injection against the decoder was performed for this branch.
