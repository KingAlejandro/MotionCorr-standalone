# WIP: end-of-run PDF tail (item 4) and alignment round-trips (item 6)

Stopped by the coordinator before any source change. No production code is
changed on this branch beyond 93c3897 (--profile_device_timing). Nothing here
is a wall claim; no kit `compare` was run.

Binary: build-dt (93c3897, Release, CUDA, nvCOMP). GPU0 A100, payload CPUs
96-103, 24-movie tutorial, canonical options.

## Item 4: the PDF tail (MEASURED, single runs, not paired)

Built with -DTIMING=ON (same source), one run:

| stage | ms |
|---|---|
| joint star and logfile pdf (total) | 726.6 |
| out - joint star scan (W_SCAN) | 8.4 |
| out - joint hist eps (W_HISTEPS) | 10.8 |
| out - gs header+batch (W_GS_HEADER, header and batch run concurrently) | 343.9 |
| out - gs batch.pdf inner (W_GS_BATCH) | 343.8 |
| out - gs all_batches.pdf (W_GS_ALLB, a copy since #127) | 1.4 |
| out - gs logfile.pdf (W_GS_LOGFILE) | 361.8 |

`--profile` run of the same binary: "joint star and logfile pdf" 736 ms, main
CPU 22.8 ms, so the main thread waits on gs almost all of that time. The
nsys trace (`trace-base-dt.report.md`, device timing off) puts "after last
movie" at 920 ms.

Standalone replays (3 repeats each): gs header 0.145 s, gs batch 0.34 s, gs
logfile concat 0.356 s, gs start/exit with nothing to do 0.07 s.

Candidate, not implemented: replace the last two passes with ONE gs pdfwrite
over `@header.pdf.lst @batch.pdf.lst` -> logfile.pdf. Replayed: 0.364 s
(1 CPU) instead of 0.34 + 0.36 s, about -0.35 s per job. The output was
rasterised (png16m at 72/150/300 dpi): 30/30 pages pixel-identical to
logfile.pdf, txtwrite text identical, MediaBox 800x800 in both. Still to do:
header.pdf, batch.pdf and all_batches.pdf must keep being produced (or the
change must be argued); the all_batches accumulation for --only_do_unfinished
re-runs must hold (an existing all_batches.pdf is prepended); keep the
JointStarPublication, PdfConcat and OutputStageFaults behaviour; --skip_logfile
unchanged. UNRUN.

## Item 6: alignment round-trips (MEASURED, one nsys trace, device timing off)

Per movie, movies 2-24, from trace.sqlite (deleted after analysis):
- patch alignment: about 50 shift round-trips per movie (D2H + host update +
  H2D), 9.5 ms of device idle inside them, about 189 us each; 11.3 ms idle
  before the first kernel (workspace reserve, cudaMemGetInfo, plan, module
  load); sync-blocked idle (kit) 2.64 ms.
- global alignment: 2.9 round-trips, 3.1 ms idle in them; 16.7 ms before the
  first kernel (per-call cudaMalloc/plan/free in cudaAlignPatchDevice).

So moving the update onto the device would at best remove about 9.5 ms + 3 ms
of device idle per movie. The larger idle in both stages is setup, not the
convergence round-trip. Device-side exact convergence (double sum of float
squares, std::sqrt, < 0.5) is not implemented and is UNRUN.
