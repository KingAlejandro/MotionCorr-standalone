# Device EER renderer: feasibility result (#193 option 2, W-EER-DEV)

**Decision: GO for proposing an integration.** All four pre-declared conditions hold on the standalone experiment, with the
conditions and caveats below. Nothing here is integrated: `src/` is unchanged and `motioncorr` does not use this code.
The integration itself still needs a maintainer decision on corrupt-fraction semantics (D6) and the complete-product gate (end of this file).

| condition | result |
|---|---|
| Exact counts in all cases | **Met.** 15 corpus configurations + 3 uint16 re-runs + 14 synthetic encodings/detectors: 0 differing pixels, equal electron counts |
| Malformed input fail-closed, sanitizer clean | **Met**, and the host's skip semantics can also be reproduced exactly (opt-in `--on_corrupt skip`); `compute-sanitizer --tool memcheck`: 0 errors in 25 runs |
| Resolved saving ≥ 1.0 s/movie or ≥ 25 % of host render | **Met on every timed case**: saving 1.05–8.37 s, device = 5–29 % of the host render time, 8 balanced AB/BA pairs each |
| Stated device-memory bound incl. 8192² | **Met**: no VRAM beyond the output stack and a `d_Fframes`-sized arena; 8192² × 144 admitted at 76.0 GiB, refused with ≥ 8 GiB reserve or on a 40 GiB card, before any allocation |

## What was built

`experiments/eer_device/` (separate nvcc/CMake build, `build.sh`; not referenced by the top-level `CMakeLists.txt`).

- **Index:** LibTIFF walks the directories (same format checks as `EERRenderer::read`, plus: every directory must agree with the first, every strip must lie inside the file, strips must not overlap and must not be empty). `pread` of the raw strips in parallel straight into a small pinned ring (4 × 64 MiB), H2D per chunk, so reading chunk k+1 overlaps the copy of chunk k.
- **Decode:** one CUDA thread per fraction, transcribing the host loops for 65000 (8+4), 65001 (7+4) and 65002 (7+2). Every bit consumed is checked against the fraction's own byte length. Electrons are scattered with integer atomics into the group's frame: **float** (exact, integer adds) or uint16. Output geometry covers `--eer_upsampling` 1, 2 and −1 on 4096² and 1, 2 on 2048² detectors. Upsampling 3 (16384²) and the legacy non-TIFF container are not covered (the host route stays for them).
- **Arena mode (integration-shaped):** compressed strips and the per-fraction tables live in a buffer of exactly the size of main's resident Fourier stack (`d_Fframes`, `n_groups × ny × (nx/2+1) × 8` B), output goes to a float stack the size of `d_Iframes`; decode is chunked by whole fractions when the strips do not fit.
- **Admission check** runs before the first `cudaMalloc`: needed = output stack + arena + declared reserve (default 4 GiB) against free VRAM.

Source: main `1db86902` plus `experiments/eer_device` at commit `539f88fc`. The matrix and sweeps ran on earlier builds of the same sources (before the skip pass and the strip-overlap check were added); the **final binary was re-run for exactness, malformed inputs, skip semantics and the three default timing series** with the same results (`evidence/final/`). Binaries (sha256, final): `eer_device_exp` `d082877dbaa6ec53c43700864c4c5e5243226a57a922ffadc812e7150a8cb3ea`, `eer_device_exp_asan` `f94178824eb2140e11898bc63708150b484a88256d70b636d44fc27e96a47acb`. Release build (CMake forced), CUDA 12.8, sm_80.

## Inputs and encodings

| movie | file | sha256 (verified against the corpus manifest) | compression | fractions |
|---|---|---|---|---:|
| Falcon 3 (10474) | `2019-06-21_20-39-45.801_eer_data_4096x4096.eer` | `fad4d37cc4b7b73076e3dd94c44be8a343f37f60b218e8057424b2154c9878ba` | **65001** | 2331 |
| Falcon 4 (10474) | `FoilHole_10919949_..._001116_Fractions.mrc.eer` | `2a46fd6123a7240e95acb324681c281964ec21da9037e05d66d9ab37319e9fed` | **65001** | 5782 |
| 12963 | `FoilHole_4674725_..._014501_EER.eer` | `3fc5feb61f487f0f4f6ec1317ae033138fe50e7da80e3b5b16bab3aaff2403f5` | **65001** | 1911 |

All three are BigTIFF, one strip per directory, 4096². No corpus file uses 65000 or 65002; those decoders (and 2048² detectors) are covered only by synthetic files written by `eer_fixture.cpp` and are labelled synthetic below.

## Exactness

Every pixel of every group against `EERRenderer::renderFrames<float>` (float output) or `<unsigned short>` (uint16 output) on the same file, plus the per-group electron counts (`evidence/matrix/*.verify.json`, final binary in `evidence/final/exact/`).

| movie | grouping (groups, unused tail) | ups 1 | ups 2 (8192²) | ups −1 (2048²) |
|---|---|---|---|---|
| Falcon 3 | 40 (58, 11) | EXACT (float, uint16) | EXACT | EXACT |
| Falcon 3 | 48 (48, 27) | EXACT | EXACT | – |
| Falcon 4 | 40 (144, 22) | EXACT (float, uint16) | EXACT | EXACT |
| Falcon 4 | 50 (115, 32) | EXACT | EXACT | – |
| 12963 | 49 (39, 0) | EXACT (float, uint16) | EXACT | EXACT |
| 12963 | 40 (47, 31) | EXACT | EXACT | – |

0 mismatched pixels in all (largest: 9.66 × 10⁹ pixels, Falcon 4 ups 2). Synthetic parity (`evidence/final/malformed/syn.*.json`): 65000, 65001, 65002 on 4096² (ups 1, 2, and −1 for 65000/65001) and 2048² (ups 1, 2): 14 of 14 EXACT. The tail fractions beyond `n_groups × grouping` are dropped, as in the runner (`nn = nframes / eer_grouping`). Chunked decode (6 chunks, forced) and the natural 2-chunk ups −1 cases are EXACT too.

## Timing

Protocol: `numactl --cpunodebind=1 --membind=1 taskset -c 96-103`, GPU0 by UUID, locks `gpu0-correctness` + `bench` held only for the timed series of one case. One discarded warm-up per arm, then **8 retained pairs in alternating AB/BA order** (A = host, B = device). Foreign CPU on 96–103 was ≤ 0.113 cores in every series (gate 0.25; 10 s pre-sample also clean); GPUs 1–3 were sampled during each series (some activity in 5 of 9, `evidence/matrix/*.gpu-samples*.csv`). Page cache warm. THP `madvise`.

- **Host arm:** `EERRenderer::read` + `renderFrames<unsigned short>` per group, 8 OpenMP threads, images retained until the end of the arm (the app's compact route; it excludes the later upload + expansion, ~0.56 s on Falcon 4 per #193, which the device route also avoids but I did not measure).
- **Device arm:** from the file path to float group frames ready in VRAM and error flags read back (index walk, read + H2D, decode). It excludes gain application and everything downstream, and the one-off allocation of the pinned ring (0.25–0.33 s) and of the device buffers (< 30 ms), which a session holds across movies.

| case | host render s median (min–max) | device e2e s | saving s median (min–max) | device / host | CPU s host / device |
|---|---|---|---|---:|---|
| Falcon 4, 40, ups 1 | 8.67 (8.59–9.77) | 0.440 (0.434–0.481) | **8.23 (8.14–9.28)** | 0.051 | 49.3 / 1.41 |
| Falcon 3, 40, ups 1 | 3.70 (3.60–3.87) | 0.343 (0.341–0.346) | **3.36 (3.25–3.53)** | 0.093 | 20.9 / 0.71 |
| 12963, 49, ups 1 | 2.74 (2.68–2.89) | 0.267 (0.265–0.267) | **2.47 (2.42–2.63)** | 0.097 | 15.6 / 0.51 |
| Falcon 3, 40, ups 2 | 7.12 (7.06–8.14) | 0.361 (0.360–0.383) | **6.76 (6.70–7.76)** | 0.051 | 46.0 / 0.70 |
| 12963, 49, ups 2 | 4.86 (4.81–5.24) | 0.286 (0.285–0.287) | **4.57 (4.52–4.96)** | 0.059 | 32.2 / 0.50 |
| Falcon 4, 40, ups −1 | 4.63 (4.58–4.99) | 0.592 (0.591–0.596) | **4.03 (3.98–4.39)** | 0.128 | 19.1 / 1.68 |
| Falcon 3, 40, ups −1 | 1.99 (1.97–2.29) | 0.514 (0.513–0.515) | **1.48 (1.45–1.77)** | 0.257 | 8.1 / 0.69 |
| 12963, 49, ups −1 | 1.47 (1.46–1.54) | 0.428 (0.425–0.450) | **1.05 (1.03–1.09)** | 0.291 | 6.3 / 0.51 |
| Falcon 4, 40, ups 2 | not run (see below) | 0.536 (0.534–0.539) | – | – | – / 1.44 |

Every one of the 64 pairs has a positive saving; the bar (≥ 1.0 s or ≥ 25 %) is met in all 8 timed cases, the smallest being 12963 at ups −1 (1.05 s, 71 %). The median saving is at least 4.6× the min–max spread of the paired savings in every case, so no separate null (AA) series was run. **Falcon 4 at ups 2 has no host arm (UNRUN):** the retained uint16 stack would be 18 GiB against ~13.7 GB free on NUMA node 1; forcing it would drive page-cache reclaim on the node every lane shares. Its device time is measured and its exactness is verified (host verification uses 8 × 128 MiB, not 18 GiB).

Final binary, default cases, 8 pairs (`evidence/final/timing/`): Falcon 4 8.80 → 0.435 s (saving 8.37, min 8.20), Falcon 3 3.78 → 0.341 s (3.43, min 3.34), 12963 2.69 → 0.265 s (2.43, min 2.41).

Device time split (median s, Falcon 4 / Falcon 3 / 12963, ups 1): index walk 0.051 / 0.065 / 0.044; read + H2D 0.158 / 0.068 / 0.046; **decode kernel 0.225 / 0.206 / 0.172**. The decode is latency-bound (one thread per fraction, ~370 k serial codes each) and nearly independent of movie size; block size 32–64 is best (`evidence/sweeps/`).

**CPUs freed.** The host render keeps 5.7 CPUs busy for 8.7 s on Falcon 4 (49 CPU-s). The device route needs readers only: reader threads 1 / 2 / 4 / 8 give Falcon 4 e2e 0.905 / 0.723 / 0.476 / 0.434 s at 0.69 / 0.96 / 0.89 / 1.39 CPU-s (Falcon 3: 0.533 / 0.405 / 0.367 / 0.339 s at 0.33 / 0.35 / 0.48 / 0.69 CPU-s). Even one reader thread is 9.6× faster than the 8-thread host render.

## Device memory

Working set = compressed strips (H2D bytes) + per-fraction tables (20 B/fraction: error, electron count, offset, length) + output. The decoder allocates nothing else; `cudaMemGetInfo` used after decode minus (output + arena) was ≤ 2 MiB (`evidence/matrix-tables.md`).

| case | compressed GiB | tables MiB | output (float) GiB | `d_Fframes` equivalent GiB | strips + tables as share of arena | decode chunks |
|---|---:|---:|---:|---:|---:|---:|
| Falcon 3, 40, ups 1 | 1.13 | 0.04 | 3.62 | 3.63 | 31 % | 1 |
| Falcon 4, 40, ups 1 | 2.72 | 0.11 | 9.00 | 9.00 | 30 % | 1 |
| 12963, 49, ups 1 | 0.81 | 0.04 | 2.44 | 2.44 | 33 % | 1 |
| **Falcon 3, 40, ups 2** (58 groups) | 1.13 | 0.04 | 14.50 | 14.50 | 8 % | 1 |
| **12963, 49, ups 2** (39 groups) | 0.81 | 0.04 | 9.75 | 9.75 | 8 % | 1 |
| **Falcon 4, 40, ups 2** (144 groups, 8192²) | 2.72 | 0.11 | 36.00 | 36.01 | 8 % | 1 |
| Falcon 4, 40, ups −1 | 2.72 | 0.11 | 2.25 | 2.25 | 121 % | 2 |
| Falcon 3, 40, ups −1 | 1.13 | 0.04 | 0.91 | 0.91 | 125 % | 2 |
| 12963, 49, ups −1 | 0.81 | 0.04 | 0.61 | 0.61 | 133 % | 2 |

- **Can it run in the borrowed `d_Fframes` arena with zero additional VRAM?** Yes in this experiment: strips and tables fit in the arena in one pass for ups 1 and 2 (8–38 % of it), and when they do not (ups −1, whose frames are 2048²) the decode is chunked by whole fractions into 2 chunks, EXACT. **Chunk size needed:** at least the largest fraction, 0.46–0.53 MB here, plus the tables; any capacity above that works (forced 4 MiB chunks: 6 chunks, EXACT). Each extra chunk serialises on a small table copy, so ups −1 on Falcon 4 spends 0.35 s in read + H2D instead of 0.16 s; a double-buffered table would remove that.
- **UNRUN:** the arena here is a separate allocation of the same size, not a real borrow through `fourier_guard.beginIngestScratch()`; the zero-extra-VRAM claim is by construction, not observed inside a session.
- **Output:** the decoder writes float counts directly, so there is no uint16 stage on the device. A uint16 output (and a non-arena layout: separate strip buffer + tables) is also exact, for reference.
- **Bound (8192² included):** `VRAM = output stack + d_Fframes-sized arena (+ nothing)`; admission needs that plus the declared reserve. Falcon 4 at ups 2: 36.0 + 36.0 = **72.0 GiB** + 4 GiB reserve = 76.0 GiB against 78.8 GiB free on the A100-80GB → **admitted and exact**. With reserve 8 GiB (80.0 GiB) or 12 GiB (84.0 GiB), or on an emulated 40 GiB card (`--vram_limit_mib`), the run is **refused before any allocation** (`cudaMalloc_calls_by_experiment = 0`; `evidence/matrix/f4-g40-u2-admit-*.verify.json`). The 4 GiB reserve (CUDA context, cuFFT workspace, gain, patch scratch) is a declared model, not measured in a session; a real integration must use main's own reserve.
- **Host:** 257 MiB pinned ring, independent of movie size.

## Malformed input

Fixtures: 48 real Falcon 3 fractions with per-fraction mutations (`mut48.eer`, manifest `evidence/mut48.manifest.json`), file-level variants (`trunc_last`, `trunc_file`, `empty_strip`), and crafted streams (overshoot, last pixel, trailing bytes, never-closing runs). Host verdicts come from one `EERRenderer` process per fraction (release and an AddressSanitizer build of the same `renderEER.cpp`); device verdicts from `dev-frames` and, for grouped products, `compare`. Device: `compute-sanitizer --tool memcheck`, 25 runs, **0 errors**; 6 runs (`trunc_file`, `empty_strip`) are refused at the index before any CUDA call; device output identical across repeated runs and under memcheck (15 of 15). Evidence: `evidence/final/malformed/`, `evidence/final/malformed-classification.md`, `evidence/final/skipsem/`.

Device modes: **fail** (default; any failed fraction rejects the movie) and **skip** (`--on_corrupt skip`: a failed fraction is re-decoded in a second pass that subtracts exactly what it added, so the frames equal what the host produces after skipping it; failed fractions are still listed so a caller can print the host's warning).

| case | (a) host renderer | (b) device, fail mode | (c) can the device match the host's skip? |
|---|---|---|---|
| Run codes overshoot the frame (`n_pix > total`), also 30 of the 35 random corruptions | `WARNING … frame is skipped` (`renderEER.cpp:564`), exit 0, fraction omitted | `ERR_RUN_PAST_END`, movie rejected | **Yes, exactly.** Skip mode: grouped products pixel-identical and electron counts equal on `mut48` at ups 1, 2, −1, also chunked and uint16; 41 fractions skipped identically |
| Stream ends before the frame closes (truncated strip 50 %, 90 %; closing code missing; 4 of the 35 random corruptions) | no strip limit in the 7-bit loop (`:427–436`): it keeps decoding into the *next fractions' bytes*; in the fixtures every such case ended in the same skip warning | `ERR_TRUNCATED` (every bit is checked against the fraction's byte length), movie rejected | **Yes where the host skips** (all of them in the fixtures). **Gap:** if the over-read happened to close the frame exactly at `total_pixels`, the host would silently accept a junk frame (not observed: 0 of the 7 truncated fractions whose host outcome is defined) and the device would skip it |
| Tiny strip (1, 3 bytes) or 1000 bytes of 127-skip codes, as the first fraction rendered | **heap-buffer-overflow WRITE** `renderEER.cpp:447` (`positions[n_electron]`; the vectors are sized `2 × strip bytes`, `:415–419`), SIGSEGV in the release build. Inside a group where a larger fraction came first the vectors are already big and nothing crashes (the grouped `compare` did not), so the outcome depends on neighbour order | `ERR_TRUNCATED`, no out-of-bounds access (memcheck 0) | **No host product exists to match** (undefined behaviour on the host). Skip mode gives the product the host produces when it does not crash |
| Last fraction truncated | **heap-buffer-overflow READ** `renderEER.cpp:436` (reads past the end of `buf`), SIGSEGV; the other 47 fractions fine | that fraction `ERR_TRUNCATED`, others ok | as above: no defined host product for that fraction; the other 47 are identical |
| Frame closes with an electron at the last pixel; valid stream followed by 64 junk bytes | accepted | accepted, identical counts | **Yes** (both accept, identical) |
| 8-bit-flip corruption that keeps the stream well formed (1 of 35 random fractions) | accepted, silently different counts | accepted, same different counts | **Yes**, and neither route can detect it: the TIFF container has no checksum, so this is an integrity limit shared by both |
| File truncated inside the last strip (byte count runs past EOF) | `TIFFReadRawStrip` return ignored (`:326`) and the size check throws `REPORT_ERROR` **inside `omp critical`** (`:296`, `:323–324`), so `std::terminate`: SIGABRT for the whole process, every fraction | refused at the index, before any GPU work | Not comparable: the host aborts the process, the device refuses the movie |
| Zero byte count in a strip (LibTIFF substitutes an estimate that runs to EOF) | same abort as above for all 48 fractions | refused at the index ("strips overlap or are empty") | as above |
| Decoded position beyond the frame | **cannot occur**: the loops stop at `n_pix >= total_pixels` before emitting, so every position is `< total_pixels` and every mapped index is in range for ups −1, 1, 2 | cannot occur; an explicit guard exists anyway. Exercised with a hook that halves the allowed index (`--clamp_div 2`): all 48 fractions `ERR_POSITION_RANGE`, 0 non-zero pixels beyond the guard, memcheck clean | n/a. UNRUN: no natural input reaches the guard |

**Gap statement for the integration.** Under current semantics the host exits 0 and omits corrupt fractions. Fail mode is therefore *not* product-identical on such input; **skip mode is, on every input where the host's behaviour is defined**, at no measurable cost when nothing fails (Falcon 3 0.340 vs 0.340 s, Falcon 4 0.434 vs 0.436 s). The residual differences are the three above: (1) the host's undefined behaviour (crash, or heap-order-dependent) has no product to reproduce; (2) a truncated strip whose over-read happens to close the frame is accepted by the host and skipped by the device; (3) container-level damage aborts the host process and is refused by the device. Whether the device route should skip, fail, or follow the host in (2) is D6.

**Host weaknesses found** (inherited code, not changed): `renderEER.cpp:427–436` unbounded 7-bit decode loop with no strip limit (OOB read past `buf`); `:415–419`, `:447` electron vectors sized from the strip length, so a corrupt short strip overflows them; `:296`, `:323–324` `REPORT_ERROR` thrown inside `omp critical` terminates the process, and `:326` ignores `TIFFReadRawStrip`'s return value. `:213` dereferences the 65007 tag value without checking `TIFFGetField` (code inspection only, not exercised).

## What an integration would still need

1. **Maintainer decision D6** on corrupt-fraction semantics (skip like the host, or fail), and D1/#134: a trust category for this decoder. It is in-tree code, bounds-checked per fraction, memcheck-clean, never writes outside its frame; unlike nvCOMP it is not vendor code, and unlike the host loop it has no unbounded read.
2. **Ingest witness value and pinnable route:** a new `--ingest_witness` value and an `--ingest` mode with the existing refusal semantics (a pinned device-EER route must refuse, not fall back, when the movie is a legacy container, upsampling 3, or fails admission). `auto` needs a rule between this route, `compact` and `float`.
3. **Complete-product gate:** strict output-tree identity (`tools/compare_output_trees.py`) of whole runs, device route against the host compact route, on the three families and the grouping/remainder/ups cases above, **including the EER gain** (12963): the decoder delivers float counts into `d_Iframes`, and the existing device gain step must be shown to give the same bytes. UNRUN here.
4. **Real arena borrow** through `fourier_guard.beginIngestScratch()` with chunking, the session's failure/poisoning rules, and the resident-retry and fallback paths (#197), which expect host frames after a device failure; a device-ingested movie has none, so those paths need a re-ingest or a host re-render.
5. **Reader integration** with main's `ChunkReaderPool`/`preadFully` instead of this experiment's OpenMP reader, and removal of the second directory walk (0.05–0.065 s).
6. **Coverage still UNRUN:** a native run of 65000/65002 on real data (only synthetic files), 2048² detectors (synthetic only), upsampling 3, legacy non-TIFF EER, multi-strip fractions on real data, and the whole-application effect of the saved upload and expansion.
7. **Headroom, not required:** the decode kernel is latency-bound at 0.17–0.32 s per movie; splitting a fraction across a warp, or overlapping chunk decode with later reads, would cut it, but the saving already clears the bar by a wide margin.

## Limitations

- One movie per family, one GPU (A100-80GB), one node and CPU mask; page cache warm; no cold-disk numbers (both arms read the same bytes).
- The device arm is not the whole run: no gain, no FFT, no downstream stages were run.
- The matrix timings were taken with an earlier build of the same sources; the final binary reproduces the three default series within 0.1 s (host) and 0.01 s (device).
- The host weaknesses were reproduced with the experiment's own harness around `EERRenderer` (one fraction per process), not through the `motioncorr` binary.
- Two superseded runs are kept out of the repository (scratch `/mnt/clathrin/alex-motioncorr-rc0/W-EER-DEV/`): a first, non-interleaved timing series without `numactl` (`evidence/prelim-uninterleaved/`, kept), and a malformed-input run whose fixture contained an empty strip that made the host abort for every fraction (first lines in `evidence/prelim-uninterleaved/attempt1-host-abort-first-lines.txt`; the empty strip is now its own fixture).

## Reproduce

```
experiments/eer_device/build.sh <build-dir> 96-103
eer_device_exp fixtures --src <Falcon3 .eer> --out <fixture-dir> --nfrac 48 --seed 1
run_final.sh <build-dir> <fixture-dir> <inputs.txt> <out-dir>      # exactness, malformed, skip semantics, default timing
run_matrix.sh / run_sweeps.sh                                       # full timing matrix and sweeps
```
