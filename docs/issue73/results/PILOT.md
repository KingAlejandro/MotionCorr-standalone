# Feasibility pilot — EMPIAR-12963, two development movies

`PROTOCOL.md` §8 step 2 (`cpu` arm) and step 3 (`cuda` arm). This page records what ran, what it
showed, and what it explicitly does not show.

## What this pilot is not

It has **104 deposited particles across two movies**. `PROTOCOL.md` §10 declares it incapable of
the primary endpoint B1, of any FSC endpoint, and of any harmful control. Nothing here is
evidence that the two backends produce equivalent *signal*. It establishes that the pipeline
runs correctly on a genuinely independent collection, and it measures image-level agreement
between arms on the movies actually compared — no more.

No confirmatory movie has been processed. No pass/fail on the scientific question is claimed.

## Provenance

| Item | Value |
| --- | --- |
| Source commit | `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` (fresh clone, clean tree, verified on both hosts) |
| Collection | EMPIAR-12963 (CC0), Melbournevirus Mini variant nucleosome, Falcon 4 EER, 300 kV |
| Input movies | sha256 `b25af46f…` and `3c8d113f…` (`results/acquisition_manifest.json`) |
| Gain | sha256 `6d4f3e5f…`, 4096² float32 LZW TIFF, symlinked to `gain.tif` so `image.h:315` detects TIFF by extension |
| Options | exactly `PROTOCOL.md` §5 as amended: `--eer_upsampling 2 --eer_grouping 47 --dose_per_frame 1.2297`, no gain rotation/flip |

The deposition form labels the gain `MRC`; the file is in fact TIFF (verified by header). The
form also lists corrected micrographs as 4096² at 0.49 Å; the deposited particle metadata says
8192² at 0.485 Å. The files were believed over the form in both cases, and the pilot confirms
the files were right.

### Binaries

| Arm | Host | sha256 | CUDA libraries |
| --- | --- | --- | --- |
| `cpu` | `cpu64` | `20b12ef4dae275e331cf19c19ddbedd99f8626d8405a6dfc9f86903eda7600db` | none |
| `cpu` | `4GPUs` | `770f82de32cba6e5e1a95517aab1aa53c95237acc7e920758545a7e8519b8f53` | none |
| `cuda` | `4GPUs` | `cc2a1573fde8313c4e400d0a099b4ca6502448b385176e5dabe4b1590092d914` | `libcudart.so.12`, `libcufft.so.11` |

Both hosts resolved the same library stack (libtiff 4.5.1, fftw 3.3.10, gcc 13.3.0), which keeps
the host contribution small. Building the `cpu` arm on *both* hosts is deliberate: it gives a
host-variation control, so any `cpu` vs `cuda` difference measured on `4GPUs` can be read against
a `cpu` vs `cpu` difference across hosts rather than assumed to be backend-caused.

## Stage 1 — `cpu` arm on `cpu64`

Both movies exited 0. Single-threaded (`--j 1`), one movie per process, `taskset -c 48-55`.

| Movie | Wall | Peak RSS | Output sha256 |
| --- | ---: | ---: | --- |
| `FoilHole_4677724_…_041554_EER` | 5:11 | 22.7 GB | `ccf2f68913c3599a0c99401b8fee540e168e3e096f88c0e4b32c01a24529a63f` |
| `FoilHole_4681533_…_062633_EER` | 5:27 | 22.7 GB | `dfb2fab4e4c9ee2c12ce51e979929d3f00466496246bd6cfd6da912a893b2f89` |

### Native format handling confirmed by execution

The runner's own log reports `Movie size: X = 8192 Y = 8192 N = 40`, and the output STAR records
`_rlnEERUpsampling 2`, `_rlnEERGrouping 47`, `_rlnMicrographDoseRate 1.229700`,
`_rlnImageSizeZ 40`. The Amendment 1 values are therefore confirmed by what ran, not asserted.

Motion was tracked normally: global alignment converged 2.85 → 0.32 px, all 25 patches converged
to 0.14–0.85 px, 85 hot pixels detected and corrected, polynomial fit RMSD X 1.96 / Y 1.54 px.

### Geometry and particle-coordinate checks

Full output in `pilot_cpu_check_*.json`.

| Check | Movie 1 | Movie 2 | Expected |
| --- | --- | --- | --- |
| Corrected size | 8192 × 8192 | 8192 × 8192 | 8192 × 8192 |
| Pixel size (MRC header) | 0.485 Å | 0.485 Å | 0.485 Å |
| Non-finite pixels | 0 | 0 | 0 |
| Deposited particles scored | 54 | 50 | — |
| AUC, deposited vs random (y as-is) | **0.912** | **0.946** | ≫ 0.5 |
| AUC, y flipped | 0.452 | 0.489 | ≈ 0.5 |

The deposited coordinates land on real particles, and the gain orientation is right as-is
(Amendment 3). The flipped control sitting at chance shows the test discriminates rather than
returning a high value for any input.

### Comparator self-test

A comparator that cannot fail proves nothing, so `i73_compare_arms.py` was checked in both
directions on the `cpu64` outputs before being used on any arm pair.

| Test | Input | Result |
| --- | --- | --- |
| Null | movie 1 against itself | absolute RMSE **0.0**, relative RMSE **0.0**, max pixel error **0.0**, bitwise identical, 0 differing pixels of 67 108 864, trajectory RMS 0.0, 0 static discrepancies, no blocking failures |
| Discrimination | movie 1 against movie 2 | absolute RMSE 0.498, relative RMSE 0.387, max pixel error 4.04, trajectory RMS 6.96 px, max per-axis 7.25 px — **3 blocking failures** raised |

So a zero result means genuine agreement rather than a broken measurement, and a real difference
is reported loudly rather than absorbed.

## Stage 2 — paired `cuda` arm

Status: **pending a GPU window.** Results, when produced, are compared with
`tools/science_issue73/i73_compare_arms.py` on the corrected micrograph and the global shift
table — before any re-estimation — against the ADR #66 §4 thresholds, with relative image RMSE
carried as a non-blocking diagnostic.

## Stage 3 — confirmatory set

**Not run and not authorized.** 350 movies need ~270 GiB of raw EER and ~445 GiB of working
space, two orders of magnitude over this issue's ≤ 2 GiB cap. See `PROTOCOL.md` §9 and
`WORKER_STATUS.md`.
