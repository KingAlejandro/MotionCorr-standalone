# Experiment A (compressed-input lookahead): no-go

Gate failed on both halves. Not implemented.

Venue: `4GPUs`, A100 80GB PCIe `GPU-eddb42fe`, mask `96-103`, 24 tutorial movies,
`--ingest nvcomp --j 8`, binary `build-base` at `a294f3b` + the device-gain change.
Raw data: [`exp4.txt`](exp4.txt), [`probe_alone.csv`](probe_alone.csv). Probe source:
[`ingest_probe.c`](ingest_probe.c).

## Thresholds, set before the run

Proceed only if the producer's work is >= 60 ms/movie **and** running it alongside an
unmodified job costs <= 0.300 s.

## Result

`ingest_probe` does exactly what the proposed producer would do and nothing else:
Pass A's scan (`TIFFSetDirectory`, tag screen, `TIFFRawStripSize` for every strip,
single-threaded, mirroring `cuda_movie_session.cu:1163-1230`) then `TIFFReadRawStrip` of
every strip under `omp parallel num_threads(8)` with a per-thread `TIFFOpen`, paced at one
movie per 340 ms. No CUDA, no gain, no mutable movie state.

| quantity | measured | required | |
|---|---|---|---|
| Pass A scan | 1.3 ms/movie | | |
| raw strip read, 8 threads | 17.4 ms/movie | | |
| **stageable total** | **18.7 ms/movie** | >= 60 ms/movie | **FAIL** |
| **contention: job wall alongside the probe** | **+0.308 s** (4/4 rounds slower, [+0.047 .. +0.327]) | <= 0.300 s | **FAIL** |

72 movie-reads, 9.51 GB read. Job wall: solo 11.913 s, alongside 12.145 s. Output digest
identical in all 12 job runs.

Even if *every* stageable millisecond were hidden, the ceiling is 23/24 x 18.7 ms x 24 =
**0.430 s (3.6%)**, and the measured contention of 0.308 s leaves a net of **-0.122 s
(-1.0%)** before any of the producer's own overhead — thread, ring, claim key,
cancellation, backpressure. PR108 used this structure and lost 0 of 9 paired blocks.

`OMP_WAIT_POLICY=PASSIVE` does not recover the contention (+0.321 s), so the spinning
OpenMP workers are not its source; it does cut CPU-seconds as expected (19.03 -> 16.07).

## Why the design over-estimated this

The design put the prize at ~1.9 s from `compressed read/repack 50.9 ms` plus ~30 ms/movie
of unattributed time suspected to be Pass A. Measured here, Pass A is **1.3 ms**, not ~30,
and the read is **17.4 ms**, not 50.9 — the 50.9 ms figure is a gn0004 `--j 6` number
carried unscaled to a `--j 8` host with a warm page cache.

Caveat: the probe ran warm. A cold cache would raise the read cost, but the MotionCorr job
it must overlap with is equally warm in this benchmark, so the comparison holds for this
workload. A cold-cache or network-filesystem venue could change the answer.

## Consequence for the fallback

The design's fallback was to parallelise Pass A in place, estimated at 0.6-0.7 s. Pass A is
**1.3 ms/movie = 31 ms across 24 movies**, so that is worth at most 31 ms. Also dropped.
