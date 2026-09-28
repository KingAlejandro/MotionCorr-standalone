# WORKER_STATUS — issue #26

| field | value |
| :-- | :-- |
| Issue | [#26](https://github.com/KingAlejandro/MotionCorr-standalone/issues/26) — current-main CPU/CUDA operating envelope |
| Model | `claude-opus-5` (Opus 5, 1M context), high effort |
| Task class | measurement |
| Phase | Phase 0 + Phase 1 series executing on both hosts |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (= `origin/main` at start) |
| Branch | `round96/26-claude-opus-5` |
| Head | see `git rev-parse HEAD` |
| Draft PR | not yet opened |

## Scope

Owns the one shared operating-envelope study and this round's initial GPU benchmark slot.
Contract is `agents/designs/issue_26_operating_envelope.md`. No file under `src/` is touched.

## Changed files

| Path | Kind |
| :-- | :-- |
| `agents/designs/issue_26_operating_envelope.md` | measurement ADR and whitelist |
| `tools/envelope_runner.py` | measurement runner |
| `WORKER_STATUS.md` | this file |
| `docs/operating_envelope_issue26.md` | report and operating guide (pending) |
| `docs/benchmark_logs/issue26_envelope_*/` | raw per-run records (pending) |

## Allocation held

| Resource | State |
| :-- | :-- |
| `4-gpu-vm` `/tmp/motioncorr-bench.lock` | **held by this task** for the Phase 0/1 series |
| `4-gpu-vm` CPUs | `taskset -c 96-111` (16 logical, all NUMA node 1), verified inherited |
| `4-gpu-vm` GPUs | GPU 0 only (`GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`); 1/2/3 left free |
| `cpu64` `/tmp/motioncorr-issue96-cpu-measure.lock` | **held by this task** for the CPU series |
| `cpu64` CPUs | `taskset -c 0-31` (= NUMA node 0). Lane 32-63 untouched and free for other workers |
| `cpu64` validation lock | **not** held; no whole-host run is planned |

Other tasks: GPU is in use until the series below completes. Post NEEDS_GPU on your own issue
and it will be scheduled after this slot; do not start a competing timed job, and note that a
build also perturbs a timed run even though it produces no number.

## Builds (frozen, Release)

| Build | Host | Binary `sha256` | Flags |
| :-- | :-- | :-- | :-- |
| `build-cuda` | 4-gpu-vm | `d80cdadb9c6c5e12020dcd7dba955b3758803f6aaa51456b8d2b935f6a89789d` | `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, `sm_80`, `TIMING=OFF` |
| `build-cuda-timing` | 4-gpu-vm | `22e59177ee0b3b3da27bedd0a80318b0741e1d67c742cc2e5b6a3534cc9c28dd` | as above, `TIMING=ON` |
| `build-cpu` / `build-cpu-timing` | cpu64 | recorded in `evidence/build/` | `-O3 -DNDEBUG`, `CUDA=OFF` |

gcc 13.3.0, CUDA 12.8.61, driver 570.86.10, FFTW 3.3.10, libtiff 6.0.1.
Source archive `6d5de8340ad9469c0572767b3af7853ab4fcec030f9286870f507b6db4fe966d`, 650 files,
tree digest `787a3061e3fde06446884c405e48192c387dc5d284f4712c0b735c31185b4ba0`.

## Fixtures (verified against `docs/reference_gates.md`)

- 24-movie STAR `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041`
- gain `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`
- movie 00021 `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`
- declared 4-movie screening subset `ed74c9ed3fafdc64fa510265798bc864b1ba36b59730be4a6f9ebda1e3dc09f1`
  (00021, 00029, 00042, 00049) — **byte-identical STAR on both hosts**

## Latest results

- GPU warm-up, 24 movies, `--use_own --gpu 0 --j 8`, 5x5 patches, dose weighting: 28.98 s, exit 0,
  109 products.
- Phase 0 baseline, same configuration: **29.03 s**, exit 0, 109 products.
- Both CPU builds on cpu64 configure and build clean; binary smoke-runs.

## Blockers

None open. One cleared: see below.

## Findings so far

1. **`/tmp/motioncorr-bench.lock` was held for 2d 2h by a dead job.** Two orphaned `matrix.sh`
   sampler subshells (PIDs 17903/17904, `ppid=1`) from the issue-53 run held the box-wide
   mutex on inherited fd 3 while their driver was gone; `matrix.txt` never got past its header
   line. Archived to `/home/alex/orphaned-i53-sampler-archive-20260928` and cleared with
   Alex's explicit authorisation. No issue-53 result was lost — none had been produced.
2. **A fresh CUDA configure fails on current main with CMake 3.28.** `CMakeLists.txt:59`
   guards its `CMAKE_CUDA_ARCHITECTURES 80` fallback with `if(NOT DEFINED ...)`, but
   `enable_language(CUDA)` already defines the variable, so the fallback never fires and
   generation fails with `CUDA_ARCHITECTURES is empty`. Every caller in the repo — README, CI,
   both sbatch harnesses — passes `-DCMAKE_CUDA_ARCHITECTURES=80` explicitly, which is why it
   has stayed hidden. Reported, not fixed: `src/` and `CMakeLists.txt` are outside this
   issue's whitelist.
3. **`--max_io_threads` above `--j` is silently clamped** (`motioncorr_runner.cpp:1280`), so the
   nominal 4x4 j/IO grid contains only **10** distinct effective treatments, not 16.

## NEEDS_GPU

Not applicable — this task holds the slot.

## Next step

Complete the Phase 0/1 GPU series and the cpu64 j/binding series, compare products per arm,
write `docs/operating_envelope_issue26.md`, open the draft PR.
