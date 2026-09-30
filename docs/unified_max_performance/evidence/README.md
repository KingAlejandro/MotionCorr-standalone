# Retained campaign evidence

Venue: `4-gpu-vm`, one NVIDIA A100 80GB `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`,
8 logical CPUs pinned with `taskset -c 96-103`, CUDA 12.8, GCC 13.3,
nvCOMP 5.3.0.16, LibTIFF 4.5.1 (libdeflate backend), THP `madvise`.

Inputs: RELION 3.0 SPA tutorial, 24 movies, `movies.star`
sha256 `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041`.

| file | what |
|---|---|
| `FINAL-table.txt` | headline contenders, 5 repeats, **each arm at its own best operating point**, with every raw observation |
| `per-arm-best.txt` | the per-arm operating sweep the best points came from |
| `sweep-table-full.txt` | operating envelope, `--j` 2–8 x `--max_io_threads` 2–8, writer on and off, 3 repeats |
| `matrix.txt` | main-functionality support matrix, candidate vs main under identical options |
| `memory.txt` | VRAM sampled by device UUID, host max RSS, pinned reservation |

## Reading these honestly

- `FINAL-table.txt` supersedes an earlier 5-repeat run that imposed the
  candidate's operating point on main. That penalised main by ~7 s because
  `--max_io_threads 4` throttles the host reader main depends on, and it
  reported ×2.66. The retained figure is ×2.05.
- This run is noisier than `sweep-table-full.txt` (nvCOMP 12.66–15.59 s here
  against 13.07–13.50 s there). Arms were interleaved, so the ratio is matched,
  but the absolute numbers carry that spread.
- `matrix.txt`'s four `UNSUPPORTED-BY-MAIN` rows are cases main itself refuses
  on this fixture and the candidate refuses identically. They are not candidate
  failures and not evidence that the option is unsupported in general.
- `memory.txt`'s `peak host VmHWM` column is a harness artefact — it sampled the
  wrapper, not the child. Use `max RSS from time -v`.
- Everything here is same-backend byte equality and wall time on one dataset.
  No scientific-equivalence claim, no multi-GPU result.
