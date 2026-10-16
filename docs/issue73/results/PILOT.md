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
| **`cpu`** | **SCARF** | `e7e9c9b08939d6bf9044ba6a1972e360530ebbb80630d5537635ea24f2596311` | none |
| **`cuda`** | **SCARF** | `b09ece2490974bdb2f1aa7ef956563783476f06bf55c98d0a22c825822ac2eb0` | `libcudart.so.12`, `libcufft.so.11` |

The two SCARF binaries are the paired arms actually compared. Compilers: `cpu64` Ubuntu 24.04
gcc 13.3.0; SCARF Rocky 9 gcc 11.5.0; CUDA 12.4.0 from the facility's existing module tree
(`/apps20/sw/easybuilt/rocky/9/generic/software/CUDA/12.4.0`), `-DCMAKE_CUDA_ARCHITECTURES=80`.
Nothing was installed on any host. The CPU arms are configured `-DCUDA=OFF` (`CMakeLists.txt:56`)
and `ldd` reports no CUDA library on them.

### Exact commands

Both arms, identical but for `--gpu 0` on the `cuda` arm:

```
motioncorr --i stage/movies/<MOVIE>.eer --o <OUT>/ \
  --use_own --j 1 --seed 1 \
  --dose_weighting --dose_per_frame 1.2297 \
  --patch_x 5 --patch_y 5 --bfactor 150 \
  --eer_upsampling 2 --eer_grouping 47 \
  --gainref stage/meta/gain.tif --angpix 0.485 --voltage 300     [--gpu 0]
```

Gain-orientation control adds `--gain_rot {0,1,2,3} --gain_flip {0,1}`. Analysis:

```
python3 tools/science_issue73/i73_compare_arms.py \
  --a-mrc <CPU>.mrc --a-star <CPU>.star --b-mrc <CUDA>.mrc --b-star <CUDA>.star \
  --a-label cpu --b-label cuda

python3 tools/science_issue73/i73_check_pilot.py \
  --mrc <ARM>.mrc --movie FoilHole_4677724 \
  --passthrough stage/meta/J189_passthrough_particles.cs
```

Note the `--movie` value is the **hole ID**, not the full EER basename; see the preserved
zero-particle runs below. Particle file sha256 `171fe2ac208d9b841c8eded8d9fd0dac82599e9ddd266cb81b57729444efc122`,
verified identical on `cpu64` and SCARF.

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

Ran on SCARF Slurm job `3510296`, partition `gpu-devel`, node `gn0001`, NVIDIA A100-SXM4-40GB.
Dedicated allocation; `gpu-devel` carries a separate QOS from the `gpu` partition holding other
agents' jobs, so nothing was shared and no other allocation was delayed. **Both arms ran on the
same node against the same staged input, so the backend is the only thing that differs.**

| Arm | Movie 1 | Movie 2 | Exit |
| --- | ---: | ---: | --- |
| `cpu` | 7:34 | 8:03 | 0 |
| `cuda` | 0:37 | 0:38 | 0 |

Wall-clock is recorded as provenance, not as a benchmark: this was one run per arm on a shared
facility, with no repeats and no contention control, so it does not support a speedup claim.

### ADR #66 §4 comparator, on the corrected micrograph before any re-estimation

`tools/science_issue73/i73_compare_arms.py`. Raw output in `pilot_cpu_vs_cuda_*.json`.

| Metric | Movie 1 | Movie 2 | Threshold | Blocking | State |
| --- | ---: | ---: | ---: | --- | --- |
| absolute image RMSE | 0.014232 | 0.012418 | 0.020 | yes | WITHIN |
| max abs pixel error | 0.7756 | 1.0338 | 5.0 | yes | WITHIN |
| global trajectory vector RMS | 0.005790 px | 0.006445 px | 0.02 | yes | WITHIN |
| max per-axis global shift diff | 0.00878 px | 0.01326 px | 0.05 | yes | WITHIN |
| static STAR discrepancies | 0 | 0 | 0 | yes | WITHIN |
| relative image RMSE | 0.011061 | 0.009625 | 0.001 | **no** | EXCEEDS_NONBLOCKING |

**Zero blocking failures on both movies.** Two things this does not say. The arms are *not*
bitwise identical — 67 108 493 and 67 108 538 of 67 108 864 pixels differ, so essentially every
pixel, diffusely and at low amplitude. And relative image RMSE sits roughly 10× its ADR #66
reporting level. Per ADR #66 §4 that quantity is non-blocking and it stays non-blocking here; it
is reported because it is real, not promoted to a conclusion, and its threshold is not touched.

### Cross-host CPU control

The point of the control: a difference between arms means nothing until you know what a difference
between two *identical* backends looks like. The `cpu64` corrected micrograph for movie 1 was
moved to SCARF (sha256 `ccf2f689…` verified unchanged on arrival) and compared against the SCARF
`cpu` output for the same movie.

| Metric | `cpu` (cpu64) vs `cpu` (SCARF) |
| --- | ---: |
| absolute image RMSE | **0.0** |
| relative image RMSE | **0.0** |
| max abs pixel error | **0.0** |
| differing pixels | **0 of 67 108 864** |
| global trajectory vector RMS | **0.0 px** |

All six ADR #66 §4 checks are **WITHIN** at exactly 0.0. Two independently built CPU binaries —
`cpu64` (Ubuntu 24.04, **gcc 13.3.0**) and SCARF (Rocky 9, **gcc 11.5.0**), different
distributions, different compiler major versions, separately resolved library stacks — produce the
**bitwise identical** corrected micrograph. (The two `.mrc` files have different sha256 because
the MRC header carries per-run text labels; the pixel data is identical.)

That makes the comparison sharp rather than reassuring. The cpu-vs-cuda difference **cannot** be
attributed to host or build variation, because host and build variation on this collection is
exactly zero. The ~1 % relative RMSE between arms is attributable to the CUDA backend itself. It
is well inside every blocking threshold in ADR #66 §4, and it is not noise in the measurement.

### Particle-coordinate check replicated on the `cuda` micrographs

Geometry on both `cuda` outputs: 8192 × 8192, 0.485 Å, zero non-finite pixels — matching the `cpu`
arm. Raw output in `pilot_scarf_cuda_check_*.json` and `pilot_scarf_cpu_check_*.json`.

| Movie | Particles | AUC `cpu` | AUC `cuda` | AUC `cuda`, y flipped |
| --- | ---: | ---: | ---: | ---: |
| `FoilHole_4677724_…` | 54 | 0.9120 | 0.9110 | 0.4517 |
| `FoilHole_4681533_…` | 50 | 0.9465 | 0.9461 | 0.4898 |

The `cuda` arm recovers particle signal at the deposited coordinates indistinguishably from the
`cpu` arm (ΔAUC 0.0010 and 0.0004), with the flipped control at chance in both arms. The SCARF
`cpu` values reproduce the `cpu64` values exactly, as bitwise identity requires.

**A failed run, preserved.** The first pass of this check returned **0 particles** on every
micrograph. The cause was operator error, not data: `--movie` was given the full EER basename
`FoilHole_4677724_041554_EER`, but the deposited `location/micrograph_path` matches only the hole
ID `FoilHole_4677724`. The SCARF copy of the particle file was verified byte-identical to the
`cpu64` copy (both sha256 `171fe2ac…`), so the "missing particles" hypothesis was wrong. The
zero-particle outputs are kept in `zero_particle_runs/` rather than discarded, because a check
that silently scores nothing looks exactly like a check that passed.

## Stage 2b — gain-orientation control (Amendment 5, executed)

Eight dihedral transforms of the gain, one movie, `cpu` arm on `cpu64`, no new download. Full
record in `PROTOCOL.md` Amendment 6; raw artifacts in `gain_orientation/`.

The outcome is the **negative** branch prespecified in Amendment 5. Particle AUC across all eight
orientations spans only 0.9104–0.9153 and the frozen identity setting ranks **fourth of eight**,
so the AUC test cannot verify gain orientation and that assumption stays **unverified**.

This is not because the transforms do nothing. The gain is strongly non-uniform (mean 1.0043,
std 2.3249, CV 2.31, max 2234.9; only 31 % of pixels within 1 % of the mean), and rotating it moves
the corrected micrograph by absolute RMSE **0.047–0.080** — 2.3–4× the ADR #66 §4 blocking
threshold. A plainly misapplied gain therefore changes the image a great deal and leaves particle
contrast untouched, which falsifies the premise Amendment 3 reasoned from.

It also puts the backend difference on a scale. Against the same instrument, on the same movie:

| Perturbation | Absolute image RMSE | vs 0.020 blocking threshold |
| --- | ---: | --- |
| `cpu` vs `cpu`, different host and compiler | **0.000** | within |
| `cpu` vs `cuda`, same node | 0.0124–0.0142 | within |
| Known-wrong gain orientation | 0.047–0.080 | **exceeds** |

The comparator is not insensitive — it flags a real physical misconfiguration of this collection
well above threshold — and the backend difference sits below that and inside the limit. This is an
**image-level** observation only. It is not a §7 harmful control, there is no ρ, FSC or resolution
in it, and the §7 controls remain unrun.

### What Stage 2 establishes, and what it does not

It establishes that on a genuinely independent collection the native CUDA backend produces
corrected micrographs and motion trajectories that agree with the CPU backend inside every
blocking ADR #66 §4 threshold, measured before any re-estimation step could absorb a difference.

It establishes **no scientific equivalence**. There is no FSC, no resolution, no ρ, and no harmful
control here. With 104 deposited particles across two movies this pilot is declared incapable of
the primary endpoint by `PROTOCOL.md` §10, and image-level agreement is not signal equivalence —
a point `PROTOCOL.md` makes about `CtfMaxResolution` and which applies with equal force to RMSE.

## Stage 3 — confirmatory set

**Not run and not authorized.** 350 movies need ~270 GiB of raw EER and ~445 GiB of working
space, two orders of magnitude over this issue's ≤ 2 GiB cap. See `PROTOCOL.md` §9 and
`WORKER_STATUS.md`.
