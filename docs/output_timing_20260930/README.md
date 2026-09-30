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
(`1d7e13f`) is 30-odd commits behind this branch's parent, and comparing against
it credits this work with unrelated merged changes — a first paired run did
exactly that, reporting -5.4 s where the gain cache alone accounted for 2.3 s.

## Files

- `stage_baseline.txt` — the baseline decomposition, three repeats.
- `fs_probe.txt` — the same run with output to `/dev/shm` instead of disk.
- `campaign_cuda.txt`, `campaign_cpu.txt` — rotated multi-arm timing.
- `parity_*.txt` — product comparisons against the baseline.
- `compare_outputs.py` — the comparator: MRC core header and payload exactly,
  STAR/EPS exactly, PDF by rendered page raster, log ignoring timed lines.
- `summarise_runs.py` — the campaign summariser.
