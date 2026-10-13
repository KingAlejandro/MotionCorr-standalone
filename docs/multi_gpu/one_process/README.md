# One process, several GPUs (`--use_own --gpu 0,1,2,3`)

One worker thread per listed device; workers take whole movies from the shared list.
Source: `src/` tree `63b6249a` (base `45b57754`), the same tree as this PR's commit.

## Identity (4GPUs, 2026-10-13)

Host `4-gpu-vm`, `flock /tmp/motioncorr-bench.lock taskset -c 96-103`, CUDA 12.8, sm_80,
Release. Binaries: candidate `4a3b7337137924af`, no-mutex control `5831463a58ec3a96`
(sha256 prefixes). Input: the 24 tutorial movies (`movies.star` sha256 `fb998f70…`).
Common flags: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
--bfactor 150 --gainref Movies/gain.mrc`. Driver: [`evidence/series.sh`](evidence/series.sh),
[`evidence/identity.py`](evidence/identity.py); console in [`evidence/series.out`](evidence/series.out).

| Arm | Command | Compared with `single` |
|---|---|---|
| single | `--gpu 0 --j 2 --seed 1` | reference |
| multi | `--gpu 0,1,2,3 --j 8 --seed 1` | products identical (0 differences) |
| nomutex (negative control) | as multi, built without the defect-RNG lock | 29 files differ, products of 4 movies |
| seed2 (negative control) | `--gpu 0 --j 2 --seed 2` | products of 5 movies differ |

Comparison tool: `docs/issue85_laneC/compare_output_trees.py` with the 24-movie manifest
(MRC bytes excluding the header timestamp, normalised STARs, EPS).

- Products only (`--products-only`), single vs multi: `Validated 24 movies, 24 MRC images,
  25 STAR files, 341735520 pixels per arm / Comparison: products; status=PASS; different files=0`.
- Full tree, single vs multi: FAIL on three per-movie logs only (movies 00022-00024), and
  `different_products` is empty ([`evidence/runs/cmp-single-multi.json`](evidence/runs/cmp-single-multi.json)).
  The differing lines are device-memory diagnostics: free memory at start (77938 vs 77942 MiB)
  and the "rose by at most" figure (156 vs 160 MiB). These movies were the first on a fresh
  device in the multi arm; the chunk size is unchanged. The 4-process launcher shows the same
  difference on each device's first movie.
- Device witness: in the multi arm a single PID held compute contexts on all four GPU UUIDs, no
  foreign process was on the GPUs, and the per-movie `Device: N` log lines show 6 movies on
  each of devices 0-3 ([`evidence/runs/summary.json`](evidence/runs/summary.json)).
- The no-mutex control shows that concurrent workers do race on libc `rand()` in defect
  replacement; with the lock held from seeding to the last draw, each movie's values match the
  serial run.

The wall times in `summary.json` (single 26.9 s, multi 12.7 s) use different `--j` and one run
each; they are not a speed comparison.

`ctest -L hardware` on the same host and tree (BUILD_TESTING=ON build, binary
`48292ddf07900234`): 28/28 passed. These tests are single-device; they cover regressions in the
shared CUDA paths, not the multi-device mode.

## Timing

Pending: SCARF exclusive 4-GPU node, 96 movies, one process x 4 devices vs 4 processes x 1
device, paired and interleaved.
