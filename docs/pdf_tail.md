# End-of-run PDF tail: logfile.pdf in one Ghostscript pass

## What was there

After the last movie, `generateLogFilePDFAndWriteStarFiles()` writes the joint
STAR, six histogram EPS, then four PDFs with Ghostscript:

| pass | input | output | when |
|---|---|---|---|
| header | 6 histogram EPS (`header.pdf.lst`) | `header.pdf` | concurrently with batch |
| batch | the per-movie `*_shifts.eps` (`batch.pdf.lst`) | `batch.pdf` | |
| all_batches | earlier `all_batches.pdf` (if any) + `batch.pdf` | `all_batches.pdf` | a byte copy when there is no earlier file (#127) |
| logfile | `header.pdf` + `all_batches.pdf` | `logfile.pdf` | after header and batch finish |

On the 24-movie tutorial (A100 host, `-DTIMING=ON`, two runs) the batch pass
took 0.43–0.59 s and the logfile pass 0.39–0.44 s, in series: the logfile pass
re-encodes the two PDFs the run had just written.

## The change

With no earlier batches, `all_batches.pdf` is `batch.pdf`, so `logfile.pdf` is
the header EPS list followed by the batch EPS list. The runner now writes both
lists first, then starts three Ghostscript processes at once:

- `header.pdf` from `header.pdf.lst` (unchanged command),
- `batch.pdf` from `batch.pdf.lst` (unchanged command),
- `logfile.pdf` from `@header.pdf.lst @batch.pdf.lst` in one pdfwrite pass,
  with the same device options.

The logfile pass writes `logfile_tmp_single.pdf`, which is renamed to
`logfile.pdf` only when all three passes succeeded. `all_batches.pdf` is still
produced as before. The end-of-run tail is then about one batch pass instead
of a batch pass followed by a logfile pass.

The single pass is not used, and the original concatenation runs unchanged,
when:

- `all_batches.pdf` already exists (a rerun into the same directory, e.g.
  `--only_do_unfinished`): its pages are prepended, as before;
- either list names no EPS file (the original code's empty-PDF fallback);
- any of the three passes fails, including the single pass itself.

So the failure paths keep their outcome: a failed run leaves `logfile.pdf` as
the original code would (an earlier one untouched, or the concatenation
result), and the scratch file is always removed.

`--skip_logfile` is unchanged (it never ran the batch or logfile passes).
`--aggregate_only` uses the single pass too (it never prepends an earlier
`all_batches.pdf`); its strict checks still run on all three PDFs.

## Output equivalence

STAR and EPS files are written by the same code as before and are unchanged.
`header.pdf`, `batch.pdf` and `all_batches.pdf` come from the same commands.
`logfile.pdf` is a different Ghostscript invocation, so its bytes differ (they
already differed run to run: Ghostscript embeds dates and IDs). Its pages are
the same: rasterised with `gs -sDEVICE=png16m -r150`, every page is identical
to the original concatenation, the page count is the same, and `txtwrite` text
matches. `tests/test_pdf_single_pass.py` (CTest `PdfSinglePass`) checks this
on a two-movie run against a concatenation of the run's own `header.pdf` and
`all_batches.pdf`, and checks the rerun and failure paths. Its compiled control
`PdfSinglePassMutant_ignore_status` builds a runner that ignores the single
pass's exit status; against it only the failure arm fails.

## Not done

Rendering each movie's page on the writer thread while later movies run
(incremental rendering) would hide most of the remaining batch pass. It is not
part of this change.
