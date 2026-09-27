# I/O review evidence — PR #90 (issue #85), performance leg

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

## The headline, in one line each

* The reviewer's finding is answered at the level it was raised: decoded
  buffers are compared **pixel by pixel in order**, not by row sums, over
  740,431,779 pixels on CPU — and a row-sum-preserving permutation control
  proves the in-tree check would have missed it (§1–2).
* Corrected pixels are bit-identical across all 24 tutorial movies at `--j 1`,
  `--j 4` and CUDA `--j 8`; the only artefacts that ever differ are 4 PDFs,
  and **`main` against `main` produces the same 4** on both backends (§4).
* Timing is reported as `MEASURED`, never as a PASS: median 0.9278 pr90/main
  over 3 interleaved paired blocks, with −13.4 s of the −16.3 s attributable
  to the two stages the change touches — and the one stage that moves the
  wrong way is printed too (§11).

## Two things this evidence is not

**It is not a scientific-equivalence claim.** Every comparison here holds the
backend fixed and varies only the code head. A pass means "this change did not
alter the result on this backend", not "MotionCorr agrees with RELION" and not
"the CPU and CUDA paths agree with each other". The historical CPU/RELION
Gate 2 failures and the noisy-truth characterisation recorded elsewhere in the
repository are unaffected by anything here and remain open.

**It is not a cumulative performance claim.** The timing evidence is a paired
comparison of two heads on one machine in one allocation. Any speedup figure
quoted from an earlier cumulative head belongs to that head, not to this one.
