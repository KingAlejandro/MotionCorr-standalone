# I/O review evidence — PR #91 (issue #86), damaged-movie isolation leg

Bounded evidence gathered for the reviewed I/O split. This directory contains
the harness, the raw machine output, and one verdict document. Nothing here
changes production code, thresholds, FFT engines, precision or RNG.

```
harness/   the scripts that produced everything below
raw/cpu/   small-refmac-machine (cpu64), CPU-only builds
raw/cuda/  SCARF, exclusive A100 allocation, CUDA builds
VERDICT.md the PASS / FAIL / UNRUN matrix and what each row rests on
```

## Reading order

Start with `VERDICT.md`. Every claim in it names the file under `raw/` that
supports it, and every row that was not run says so rather than being omitted.

## One thing to read carefully

The damaged-input matrix separates two kinds of row. **Contract rows** are
graded: a damaged movie must produce a nonzero, non-signal exit, must name
itself in the failure, and must not take the healthy movies or the joint
outputs down with it. **Observation rows** are recorded and excluded from the
grade: they describe what the reader does today, whether or not anyone
considers it correct. The silent short-decode of a partially truncated TIFF is
an observation row, and `main` does the same thing — see `VERDICT.md`.

## The headline, in one line each

* PR #91 passes all 12 graded contract rows; `main` fails 6 of the same 12,
  and every one of its failures is a batch where the damaged movie came
  **first** and the healthy movies behind it were never processed (§10).
* PR #91 does **not** catch all damaged input. A truncation that leaves intact
  TIFF directories is still decoded short and processed to a clean success on
  both heads. §4 records the reproduction and proposes a follow-up acceptance
  criterion for a separate issue; no production source was changed here.

## What this evidence is not

Every comparison holds the backend fixed and varies only the code head. A pass
means "this change did not alter the result on this backend", not "MotionCorr
agrees with RELION" and not "the CPU and CUDA paths agree with each other". The
historical CPU/RELION Gate 2 failures and the noisy-truth characterisation
recorded elsewhere in the repository are unaffected by anything here and remain
open.
