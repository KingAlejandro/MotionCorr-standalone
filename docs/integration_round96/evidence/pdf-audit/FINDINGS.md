# Retained-evidence audit of the four PDF differences

Question asked: are the four failing PDFs **metadata/serialization only**, or do
they carry differing **rendered content or plot data**?

Answer, in one line: **rendered content does differ — but it is exclusively the
embedded absolute output path, and no plot datum differs.** The `overall`
verdict stays FAIL and nothing was normalised to make it pass.

Source: retained cpu64 A/B pair from the final-head all-24 run. **MotionCorr was
not re-run.** Tooling on this host is ghostscript 10.02.1 + numpy 2.5.3; no
poppler, no pypdf, no ImageMagick.

## Artifact identity

| artifact | main sha256 | candidate sha256 | bytes |
|---|---|---|---|
| `all_batches.pdf` | `d4ddb1e99aec1114…` | `b085755087592c54…` | 401934 / 402212 |
| `batch.pdf` | `d736928a73b7958d…` | `7647c64130397727…` | 402083 / 402361 |
| `header.pdf` | `544c5badd1c6204c…` | `b3e617d4f8e71bfa…` | 34263 / **34263** |
| `logfile.pdf` | `bce2dd398f5c1809…` | `f756355270f7a379…` | 434289 / 434568 |

Page counts identical: 24/24, 24/24, 6/6, 30/30.

## What differs

**1. Metadata — all four.** `/Producer(GPL Ghostscript 10.02.1)` identical;
`/CreationDate` and `/ModDate` differ by the ~3.5 minutes between the two arms
(`D:20260928024134Z` vs `D:20260928024505Z`).

**2. Rendered content — three of four.** `gs -sDEVICE=png16m -r150`, compared
pixel-by-pixel with no normalisation:

| artifact | pages | render verdict |
|---|---|---|
| `header.pdf` | 6 | **RENDER IDENTICAL** — metadata-only |
| `all_batches.pdf` | 24 | differs on 24/24 |
| `batch.pdf` | 24 | differs on 24/24 |
| `logfile.pdf` | 30 | differs on 24/30 |

**Every differing page differs in exactly one row band: rows 186–215 of 1667**
— 30 px at 150 dpi, one line of text, 1.8 % of page height, **a single distinct
row span across all 72 differing pages**. Page-1 content outside that band is
**byte-identical** (1637 of 1667 rows).

Cropping that band and looking at it (`crop_main.png`, `crop_cand.png`):

```
main:      /home/ubuntu/…/ab24/out_main-4c952b3_j8/Movies/20170629_00021_frameImage_shifts.eps
candidate: /home/ubuntu/…/ab24/out_integrate-round96-final_j8/Movies/20170629_00021_frameImage_shifts.eps
```

It is the printed EPS source path. The two arms write to differently-named
output directories **by construction of the A/B harness**, not by any code
change. Corroborated arithmetically: the directory name is 11 characters
longer, byte deltas are +278/+278/+279, implying 25.3 occurrences against the 25
expected (24 movies + 1 joint); `header.pdf` embeds no path and has a **0-byte**
delta.

## Supporting evidence (not a substitute for the PDF check)

- **EPS shift plots: 24 of 24 differ raw**, and in **all 24 every differing line
  contains the output directory** — the plot title string. All plotted
  coordinate data is identical.
- **STAR: 1 of 25 differs raw** — `corrected_micrographs.star`, 48 differing
  lines, **all 48 containing the output directory**, with the numeric columns
  (e.g. `16.419638 2.504833 13.914805`) identical on both sides.

The A/B harness reported 25/25 STARs identical because it normalises paths
before comparing. That normalisation is legitimate for a same-backend A/B, but
it is why the raw picture differs from the reported one — recorded so the two
numbers are not mistaken for a contradiction.

## Correction to a standing project assumption

These four differences have been carried since #66/#90 as *"ghostscript PDF
nondeterminism"*. That is **incomplete**. Date nondeterminism is present, but
the **rendered** difference is the embedded output path — a property of the A/B
directory layout, not of ghostscript and not of the code. `header.pdf`, the one
PDF with no embedded path, is byte-size-identical, text-identical and
render-identical apart from its timestamp.

## Limits, and what remains unverified

- Render comparison is at **150 dpi**; a difference finer than one device pixel
  at that resolution would not be resolved. The plot areas are byte-identical
  at this resolution, not proven identical at all resolutions.
- `gs -sDEVICE=txtwrite` extracts text without positions, so text placement is
  covered only through the render.
- **Not established:** that the PDFs would be byte-identical modulo timestamp if
  both arms wrote to identically-named directories. Establishing it requires
  re-running MotionCorr, which is out of scope here. The bounded command is
  prepared below rather than executed.

```sh
# Bounded confirmation, NOT run: same binary pair, identical output dir names,
# so no path can differ. Requires one all-24 pair per arm.
for arm in main cand; do
  mkdir -p /tmp/pdfctl/$arm/out            # identical leaf name in both arms
  ( cd "$TUTORIAL" && "$BIN_$arm" --i movies.star --o /tmp/pdfctl/$arm/out \
      --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
      --bfactor 150 --gainref Movies/gain.mrc --j 8 --seed 1 )
done
# then: strip /CreationDate and /ModDate only, and compare the remainder
for f in all_batches batch header logfile; do
  cmp <(sed 's/\/\(Creation\|Mod\)Date([^)]*)//g' /tmp/pdfctl/main/out/$f.pdf) \
      <(sed 's/\/\(Creation\|Mod\)Date([^)]*)//g' /tmp/pdfctl/cand/out/$f.pdf) \
    && echo "$f identical modulo timestamp" || echo "$f STILL DIFFERS"
done
```

## Disposition

`overall: FAIL` is **retained**, the four PDFs stay in the failing set, and no
exclusion or content normalisation was applied to obtain a pass. The audit
narrows *what* the failure is: metadata on all four, plus one line of embedded
path text on three. **No rendered plot datum differs between main and the
candidate.**
