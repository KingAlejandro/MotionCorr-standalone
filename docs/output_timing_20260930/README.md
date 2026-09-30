# Output-stage timing and optimisation, 2026-09-30

Where the time goes when MotionCorr writes its products, and what three changes
to that path are worth. Everything here is the 24-movie RELION 3.0 tutorial set
at 3710x3838x24, `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5
--patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8`, Release
(`-O3 -DNDEBUG`) with `-DTIMING=ON`.

Hosts: the CUDA arm on `4-gpu-vm` (A100 80GB, `taskset -c 96-103`, GPU 0 by
UUID, under `flock /tmp/motioncorr-bench.lock`); the CPU arm on
`small-refmac-machine` (`taskset -c 56-63`, under
`flock /tmp/motioncorr-cpu64-bench.lock`). Both boxes are shared. Output went to
local disk; `/dev/shm` was used only for the filesystem probe below.

## Arms

| arm | source | contents |
|---|---|---|
| `instr` | branch parent `6393547` + `c08fb29` | baseline, plus TIMING-only sub-timers that split the output stage |
| `t1` | + `cbf8dc7` | one MRC statistics pass; Ghostscript passes reduced |
| `t2` | + `92e7662`, `b796441` | plus the background output writer |

`instr` is the measurement baseline rather than `main`: the local `main` ref
(`1d7e13f`) is 113 non-merge commits behind this branch's parent, and comparing against
it credits this work with unrelated merged changes — a first paired run did
exactly that, reporting -5.4 s where the gain cache alone accounted for 2.3 s.

## Files

- `stage_baseline.txt` — the baseline decomposition, three repeats.
- `fs_probe.txt` — the same run with output to `/dev/shm` instead of disk.
- `campaign_cuda.txt` — the six-round CUDA campaign; the cleanest timing.
- `campaign_cuda_final.txt` — the final binaries at `--j 8` and `--j 6`.
- `campaign_cpu.txt` — the CPU-path campaign on `small-refmac-machine`.
- `parity_cuda.txt` — product comparison against the baseline.
- `mutants.txt`, `mutation_probe.cpp` — what the statistics test can reject.
- `ctest_instr.log`, `ctest_t2.log` — the suite, baseline and final tree.
- `compare_outputs.py` — the comparator: MRC core header and payload exactly,
  STAR/EPS exactly, PDF by rendered page raster, log ignoring timed lines.
- `summarise_runs.py` — the campaign summariser.

## Where the output time went (baseline, CUDA)

24 movies, median of the six baseline runs in `campaign_cuda.txt`, 28.7 s wall.

| stage | s | per movie | note |
|---|---|---|---|
| `write corrected image` | 2.98 | 124 ms | |
| ⤷ `out - mrc stats` | 1.37 | 57 ms | four full traversals for amin/amax/amean/arms |
| ⤷ `out - mrc payload` | 1.59 | 66 ms | one 57 MB `fwrite` |
| ⤷ open / header / close | 0.004 | | close spiked to 1.05 s once, on writeback |
| `write star and shift plot` | 0.13 | 5 ms | 0.049 STAR + 0.076 EPS |
| `joint star and logfile pdf` | 1.08 | | of which 1.06 s is four Ghostscript processes |
| ⤷ `gs header.pdf` | 0.13 | | 6 histogram/scatter EPS |
| ⤷ `gs batch.pdf` | 0.31 | | 24 per-movie EPS |
| ⤷ `gs all_batches.pdf` | 0.30 | | **re-encodes `batch.pdf` and nothing else** |
| ⤷ `gs logfile.pdf` | 0.33 | | `header.pdf` + `all_batches.pdf` |
| ⤷ joint STAR rescan, histogram EPS | 0.016 | | |
| **total** | **4.19** | | **15% of wall** |

The same output stage on the CPU path is 2.98 s of a 222.8 s run — 1.3% — so
this is a CUDA-path problem: the GPU shortens everything except the writing.

The payload split between CPU and filesystem comes from `fs_probe.txt` — the
identical run with `--o` on `/dev/shm`:

| destination | `out - mrc payload` |
|---|---|
| local disk | 1.58 s |
| tmpfs | 1.08 s |

So 1.08 s is the cost of moving 1.37 GB into the page cache and 0.50 s is the
filesystem underneath it. `out - mrc stats` is identical on both (1.31 vs
1.31 s), as a pure-CPU stage should be.

## What changed, and what each item is worth

**One statistics pass per MRC write** (`cbf8dc7`). `writeMRC` asked `MDMainHeader`
for amin, amax, amean and arms one at a time and fell back to
`computeMin()`/`computeMax()`/`computeAvg()`/`computeStddev()` separately, so a
14.2 M-pixel float micrograph was traversed four times per output file.
`computeMinMaxAvgStddev` merges them, preserving every accumulator's type,
seed, comparison form and summation order. `out - mrc stats` 1.37 → 0.40 s.

**A Ghostscript pass that re-encoded its own input** (`cbf8dc7`). With no
previous `all_batches.pdf`, `concatenatePDFfiles(all_batches.pdf, [batch.pdf])`
is a one-input concatenation, and Ghostscript re-rendered `batch.pdf` to
produce it: 0.30 s. It is now a copy when the single input starts with `%PDF`;
anything else — including the empty placeholder written when no EPS was found —
still goes to Ghostscript, so its outcome is whatever it was before.
`out - gs all_batches.pdf` 0.295 → 0.001 s.

**The two independent Ghostscript passes in parallel** (`cbf8dc7`).
`header.pdf` and `batch.pdf` read disjoint EPS sets and write different files.
0.126 + 0.310 serial → 0.315 s overlapped.

**The writes moved off the critical path** (`92e7662`). One background thread
writes movie N's products while the main thread computes movie N+1. The
main-thread cost of `write corrected image` goes from 2.03 s to 0.001 s and
`write star and shift plot` from 0.125 s to 0.001 s — the work is still done,
in `out - mrc payload`, on the writer.

## What it is worth end to end

From `campaign_cuda.txt` — six rounds, arm order rotated, 24 movies, `--j 8`:

| arm | median wall | vs baseline | rounds faster |
|---|---|---|---|
| baseline | 28.73 s | — | — |
| + one stats pass, fewer gs passes | 27.41 s | **-1.26 s (-4.4%)** | 6/6 |
| + background writer | 26.88 s | **-1.88 s (-6.5%)** | 6/6 |

Neither arm's range overlaps the baseline's. Peak RSS is unchanged at
1560 MiB: the extra in-flight micrograph is not what sets the peak.

## Consistency and robustness

**Products.** `compare_outputs.py` compares every file the two runs produced.
MRC is compared as bytes 0-223 (which covers amin/amax/amean at 76/80/84 and
arms at 216) and the payload from 1024 on; the 800-byte `strftime` label is
reported and not asserted. STAR, EPS and list files are compared byte for
byte. PDFs are compared as rendered page rasters, because Ghostscript stamps
`/CreationDate` and a time-derived `/ID`. Logs are compared after dropping the
lines that carry a duration. Both runs wrote to the same output path, one at a
time, because the path is embedded in the STAR and EPS products. Results in
`parity_cuda.txt`.

The reference is the branch's parent `6393547`, not the local `main` ref
(`1d7e13f`), which is 113 non-merge commits behind it. Comparing against that
ref would mix this work with everything already merged — the first paired run
did exactly that and attributed 5.4 s to these changes, of which 2.3 s was the
gain-reference cache.

**Fail-closed behaviour.** The property the background writer could plausibly
break is the one `tests/test_write_faults.py` asserts: a movie whose image
write fails must leave no completion record, must not enter the joint STAR, and
must be reprocessed on `--only_do_unfinished`. It is preserved structurally —
the per-movie STAR is submitted after the images into the same FIFO, and the
first failure in a group cancels the rest of that group — and the test passes.

**Test suite.** `ctest` on `small-refmac-machine`, both the baseline and the
final tree: 20 of 21 pass, including `WriteFaults`, `GlobalIfftElision` (which
covers `--even_odd_split` and `--save_noDW`, so the multi-image-per-movie path),
`Runner_resume`, `DamagedMovie`, and the new `MrcHeaderStats`.
`CiFailClosedControls` fails identically in the baseline: it shells out to a
bare `cmake`, which is not on PATH there (only `~/.mc-venv/bin/cmake`), and it
asserts on a git-ref error message that differs because the tree was staged
with `git archive` and has no git metadata. Both are artefacts of how the tree
was staged, not of these changes. Logs in `ctest_*.log`.

**What the fused statistics routine is tested against.** `MrcHeaderStats`
compares it with all four originals bit for bit over 13 cases. Five separate
mutations of it are rejected by those cases and one is not, because that one is
provably equivalent; `mutants.txt` has the record and the reasoning.

## What is left, and what was considered and not done

After the three changes, the output work still on the critical path is the
Ghostscript tail: `gs header.pdf` overlapped with `gs batch.pdf` (0.32 s) and
then `gs logfile.pdf` (0.32 s), about 0.66 s, 2.5% of wall. It is a tail: it
runs after the last movie, so there is no computation left to overlap it with,
and the only parallelism in it is the one already taken.

Considered and not done:

- **Build `logfile.pdf` in one Ghostscript pass** over the header EPS, the
  pre-existing `all_batches.pdf` and the batch EPS, concurrently with the other
  two passes. Same pages, saves about 0.2 s. Rejected for now: it changes
  `logfile.pdf` from a concatenation of two Ghostscript-produced PDFs into a
  direct render, which is a larger claim to defend than 0.8% of wall is worth.
- **Parallelising the statistics reduction.** It would change the summation
  order, and therefore amean and arms in the published header. Mutation B in
  `mutants.txt` is exactly this, and the test rejects it.
- **Fixing `computeStats`**, which has the seeding defect described above. Its
  existing callers depend on the values it returns; that is a separate change
  with its own parity question.

The largest remaining stages are not output at all: `read movie` at 7.1 s (26%
of wall) and `apply gain and initial sum` at 3.6 s (13%). Those are issues #85,
#94 and #95.

## What the background writer is worth depends on CPU headroom

The writer is one extra thread. Whether it buys the whole write back or only
part of it depends on whether a CPU is free to run it. Isolating it (t2 against
t1) at two `--j` values under the same 8-CPU `taskset`:

| `--j` | spare CPUs | t2 - t1 | rounds faster | source |
|---|---|---|---|---|
| 8 | 0 | **-0.51 s (-1.8%)** | 6/6, ranges overlap | `campaign_cuda.txt` |
| 8 | 0 | -2.05 s (-6.7%) | 3/3, ranges overlap | `campaign_cuda_final.txt` block 1 |
| 6 | 2 | **-2.65 s (-7.9%)** | 3/3, no overlap | `campaign_cuda_final.txt` block 2 |

The two `--j 8` estimates disagree by 1.5 s, and the cleaner six-round one is
the conservative one; both have overlapping arm ranges, so at `--j 8` the
honest statement is "faster in every round, somewhere between half a second and
two". With two CPUs spare the effect is larger than the within-arm spread and
the arms do not overlap.

That is the expected shape. `--j 8` inside an 8-CPU allocation means the
OpenMP pool already covers every CPU the process may use, so the writer takes
its time back from the pipeline: the stage table for that block shows
`apply gain and initial sum` and `read movie` absorbing part of what the write
gave up. With a CPU free it does not have to.

Direct evidence that the write did leave the critical path, from the same
stage table: main-thread `write corrected image` 2.083 → 0.001 s and
`write star and shift plot` 0.126 → 0.002 s, with the work reappearing as
`out - mrc payload` 1.641 → 1.915 s, which the writer thread ticks.

## CPU path

The same output stage on `small-refmac-machine` is 2.93 s of a 216.8 s
baseline run — 1.4% — so there is much less to win, and the changes are worth
correspondingly less:

| arm | median wall | vs baseline | rounds faster |
|---|---|---|---|
| baseline | 216.76 s | — | — |
| t1 | 216.41 s | -0.78 s (-0.4%) | 3/3, ranges overlap |
| t2 | 213.41 s | -3.51 s (-1.6%) | 3/3, no overlap |

Read those as signs, not as magnitudes: the within-arm spread on that box is up
to 6 s against 1 s on the GPU host, it carries two permanent `ctffind`
processes and a baseline load1 near 9, and n=3. The useful statement is that
neither change is a regression on the CPU path and the background writer is not
one either, which was the open question — `--j 8` inside an 8-CPU `taskset`
there gives the writer thread no CPU of its own.

The stage breakdown matches the CUDA one in shape: `out - mrc stats`
1.04 → 0.35 s, `out - gs all_batches.pdf` 0.222 → 0.000 s, main-thread
`write corrected image` 2.03 → 0.001 s under the writer. Peak RSS 3253 →
3254 MiB. Numbers in `campaign_cpu.txt`.
