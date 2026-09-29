# Issue #85: which DEFLATE implementation actually decodes the movies

Source: main `a75a3f87f7ef17e0a29b1c91a1edecda08ebed34` plus this branch's diff.
Measurement host `cpu64` (`small-refmac-machine`). Exact revisions, hashes,
resources and every check: `validation.txt`. Per-run numbers: `results.json`.
Scripts as they ran: `harness/` — a transcript with absolute paths from the run
directory, not a portable tool.

## Result

**The largest attributed component of #85's movie-read cost was already on the
fast codec.** LibTIFF can service Deflate with either zlib or libdeflate. On
both project hosts the installed LibTIFF 4.5.1 uses libdeflate for every strip,
so the `Deflate 3.409 s` of the lane A attribution was libdeflate, not zlib.
There is no codec change to make there, and no custom decoder is justified.

**What the configuration is worth, and who is losing it.** With one MotionCorr
binary and two LibTIFF 4.5.1 builds differing only in libdeflate support, the
`read movie` stage over the 24 tutorial movies is **5.68 s with libdeflate
against 9.93 s with zlib, −42.9%**, with byte-identical products. Rocky/RHEL 9
and Homebrew ship LibTIFF without libdeflate, so the same source silently pays
that on those systems — including SCARF.

The change this evidence supports is therefore a build-configuration one: the
configure step now reports which backend the linked LibTIFF will use. No
production source file changes, and no new dependency is added.

## 1. Which decoder actually runs

Nothing in `TIFFGetVersion()` says which subcodec is in use, and a report that
labels a cost "zlib" is not evidence that zlib decoded anything. Two
independent observations were taken, and they agree.

**Runtime call counts.** `harness/codec_witness.c` is an `LD_PRELOAD`
interposer on both APIs — `inflate` / `inflateInit_` and
`libdeflate_alloc_decompressor` / `libdeflate_zlib_decompress` /
`libdeflate_deflate_decompress` — forwarding through `dlsym(RTLD_NEXT, ...)`
and counting calls and output bytes. Driving the production path
(`Image<float>::read`, as `MotioncorrRunner` calls it) over
`20170629_00021_frameImage.tiff`, 24 frames x 3838 strips = 92,112 strips:

| arm | `inflate` | `libdeflate_zlib_decompress` | bytes out |
| :-- | --: | --: | --: |
| system LibTIFF 4.5.1 | 0 | **92,112** | 683,471,040 |
| matched build, libdeflate | 0 | **92,112** | 683,471,040 |
| matched build, zlib only | **92,112** | 0 | 683,471,040 |

683,471,040 = 3710 x 3838 x 24 x 2 bytes, the whole movie. Each arm accounts
for every strip, and the zlib-only arm is the negative control that shows the
counter is not simply always reporting libdeflate.

**Configure-time capability.** The new CMake check asks the library to select
`TIFFTAG_DEFLATE_SUBCODEC = DEFLATE_SUBCODEC_LIBDEFLATE`, which only a LibTIFF
built with libdeflate accepts. It was calibrated against the runtime counts
above before being used anywhere: libdeflate arm `Success`, zlib arm `Failed`,
matching the call counts on both. On macOS the CMake configure log records
`buildResult exitCode: 0` with `runResult exitCode: 1`, so the negative there
is the probe running and answering, not the probe failing to compile.

**Venue audit.** `ldd`/`otool` plus the subcodec probe on every row; the two
cpu64 rows also have the runtime call counts above.

| venue | LibTIFF | libdeflate | how established |
| :-- | :-- | :-- | :-- |
| `4GPUs` (4-gpu-vm) — lane A's venue | 4.5.1 (Ubuntu 24.04) | **yes** | `ldd` shows `libdeflate.so.0`; probe = 1 |
| `cpu64` | 4.5.1 (Ubuntu 24.04) | **yes** | `ldd`; probe = 1; 92,112/92,112 calls |
| SCARF `cn1052` | 4.4.0 (Rocky 9.8) | **no** | `ldd` shows only `libz`; `rpm -q libdeflate` not installed |
| macOS Homebrew | 4.7.2 | **no** | `otool -L` shows only `libz`, `libzstd`; probe = 0 |

The 4-GPU VM is where #85 lane A measured `Deflate 3.409 s`. That component was
already libdeflate.

## 2. Matched LibTIFF builds

Two LibTIFF builds from one upstream tarball (`tiff-4.5.1.tar.gz`, sha256
`d7f38b6788e4a8f5da7940c5ac9424f494d8a79eba53d555f4a507167dca5e2b`), configured
identically apart from `-Dlibdeflate=ON|OFF` and selected per run with
`LD_LIBRARY_PATH`. The MotionCorr executable is the same file in every run
(`d884fb5d…`), and rebuilding this branch's source in place reproduced that
exact binary, so the measurement is on the final source.

Budget: `taskset -c 0-31`, `--j 8` (which is also `n_io_threads`), page cache
warmed identically before the series, arm order alternating between reps,
input and output on local disk. 24 movies, `--dose_weighting --patch_x 5
--patch_y 5 --bfactor 150 --seed 1`; the gain mode adds `--gainref`.

| mode | metric | libdeflate | zlib | delta |
| :-- | :-- | --: | --: | --: |
| gain | `read movie` | **5.68** (5.67 / 5.68 / 5.74) | **9.93** (9.88 / 9.93 / 10.02) | **−4.26 s, −42.9%** |
| gain | wall | **208.8** (208.2 / 208.8 / 209.4) | **213.4** (212.8 / 213.4 / 219.5) | −4.61 s, −2.2% |
| no gain | `read movie` | **5.99** (5.92 / 6.06) | **10.50** (10.45 / 10.55) | **−4.51 s, −43.0%** |
| no gain | wall | 236.1 (234.9 / 237.4) | 238.6 (233.0 / 244.3) | −2.50 s, not separated |

Medians, then every rep. `read movie` is elapsed time, not an in-thread sum:
`RCTIC`/`RCTOC(TIMING_READ_MOVIE)` bracket the whole OpenMP region from the
serial path (`src/motioncorr_runner.cpp:1445-1471`).

The stage result is the robust one: all five pairs are disjoint, within-arm
spread is 0.07–0.14 s against a 4.3–4.5 s difference, and the two modes agree
to 0.1 percentage points.

**The wall claim holds in the gain mode only.** There the arms are disjoint
(slowest libdeflate run 209.4 s < fastest zlib run 212.8 s) and the −4.61 s
matches the stage difference. In the no-gain mode they overlap: `dose
weighting` ranged 78.8–80.3 s across those four runs, so a compute stage moved
by more than the read saving. Peak RSS is indistinguishable between arms
(3,331,076 vs 3,330,696 KiB gain; 3,275,194 vs 3,276,068 KiB no gain).

## 3. The two arms produce the same numbers

Every check ran under each LibTIFF arm, same binary.

| check | libdeflate | zlib |
| :-- | :-- | :-- |
| required `ctest` suite | 17/18 | 17/18 |
| exact ordered decoded samples, whole real movie | sha256 `15c49b89…` | sha256 `15c49b89…` |

The sample dump is every decoded float of all 24 frames in index order
(683 MB); the two arms are byte-identical. Flipping one float in one copy
breaks the comparison, so it is not a vacuous match.

The one `ctest` failure is `CiFailClosedControls` Control 6, which needs git
metadata the staged `git archive` tree does not have. **Unmodified main
`a75a3f8`, extracted the same way, fails the identical assertion at the same
line** (`tools/test_ci_fail_closed.py:396`), so it is a property of the staging,
not of this change. CI checks out a real repository and exercises it properly.

Complete product identity across arms, all 24 movies, both modes — MRC data
from byte 1024, the full 1024-byte header with only the `Relion dd-Mon-yy
HH:MM:SS` label stamp normalized, every `.star` and `.log`, and the project's
own `tools/compare_motioncorr.py --gate exact --require-complete-coverage`:

| comparison | MRC differing | text differing | gate failing | verdict |
| :-- | --: | --: | --: | :-- |
| same-arm rerun (libdeflate rep1 vs rep2) | 0 / 24 | 0 / 49 | 0 / 24 | IDENTICAL |
| cross-arm, gain | 0 / 24 | 0 / 49 | 0 / 24 | IDENTICAL |
| cross-arm, no gain | 0 / 24 | 0 / 49 | 0 / 24 | IDENTICAL |
| negative control: one pixel, 1 ULP | **1** | 0 | **1** | DIFFERENT |
| negative control: one STAR shift, +0.001 px | 0 | **1** | **1** | DIFFERENT |

Two negative controls because one does not reach every oracle: the pixel flip
turns the MRC-byte and gate layers red and leaves the text layer green, the
STAR perturbation does the reverse. The same-arm rerun shows the comparison can
return clean at all. EPS and PDF products are excluded: ghostscript embeds
generation dates, and their content derives from the STAR values compared here.

`TiffRead` now checks exact ordered sample values as well as row sums, and that
addition is not decorative. Swapping the two nibble branches of `castPage2T`'s
`UHalf` case (`src/image.h:922-923`) leaves every row sum bit-identical, since
a sum cannot see the order of two values inside a byte. Built against that
mutant, the pre-existing row-sum checks all pass and the new check fails:

```
  u16_deflate_rps1: 3 frame(s) 29x37, 111 row sums and 3219 samples exact
  u16_raw_rps7: 2 frame(s) 16x50, 100 row sums and 1600 samples exact
AssertionError: packed4bit_k2sr: output row 0 sample 0 differs (5.0 != 7.0)
```

## 4. What this does not establish

- **No GPU-regime measurement was taken.** The decode is host-side and
  unchanged by offload, so the ~4.3 s is expected to persist while the run it
  sits in is shorter, raising its share. That share is not measured here and no
  number is claimed for it. No SCARF allocation was used and no native GPU work
  was run.
- **One host, one input set, one thread count.** `--j 8` on cpu64 only. The
  decode is strip-parallel, so the arms' difference will scale differently at
  other thread counts, and the zlib-only venues in the audit table were not
  themselves timed — their timings would differ by CPU as well as by codec.
- **The no-gain wall is not evidence of an application speedup**, for the
  reason given above. Only the gain-mode wall separates.
- **This does not retire #85 lane F.** It removes lane F's premise on these
  hosts — the backend is already libdeflate, so a hand-written inflate would be
  competing with libdeflate, not with zlib — but no custom decoder was written
  or measured.
- **The distro rows are current facts, not guarantees.** They will change when
  a distribution rebuilds its LibTIFF. The configure line is the durable answer;
  the table is the reason the configure line exists.
- Nothing here bears on #118 compact ingest, #121's reader pool, or #53
  scheduling. The libdeflate arm and the zlib arm are the same code path.

## 5. Provenance

See `validation.txt` for source/binary/library/input hashes, compiler and CMake
versions, host and THP setting, cpusets and locks, the background load present
throughout, and the raw result of every check above.
