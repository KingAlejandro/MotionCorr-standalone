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

## Second venue — SCARF `gnx002`, job 3515730

`scarf-3515730.log` is the full job output. Venue: A100-SXM4-40GB
`GPU-d494a7db…` (4GPUs is A100 80GB PCIe), CUDA 12.8.61 (same version),
Rocky 9, Python 3.9.25, numpy 1.22.4, allocation `Cpus_allowed_list: 0-3,16-19`.
Configured without `-DPython3_EXECUTABLE`, which is the configuration that
exposed the `NvcompGuards` registration bug.

What it establishes:

- the CUDA-without-nvCOMP link fix holds on a second toolchain (0 undefined
  references);
- `CudaNvcompReconstructionFailures` is not collected where nvCOMP is absent;
- `taskset -c 96-103` fails outright on a SCARF allocation, which is why the
  hardcoded mask had to become the optional `--cpus`;
- both reconstruction-cleanup controls pass with the same injection, cleanup
  attribution, refusal and zero-product evidence as on 4GPUs.

`CiFailClosedControls` fails there, 3 of 8 subtests, from a canonical fixture
hash mismatch. **Main fails identically on the same node**, and the generator
files are untouched by this branch, so it is pre-existing and not caused here.

Root-caused in PR #129, not here. It *is* the NumPy version, and my note that
it was not was wrong. Ruling out the RNG draw -- the generator's
`np.random.default_rng(59).normal(0, 2, 9)` is byte-identical under 1.22.4 and
2.5.3 -- does not rule out NumPy, and I over-read one negative result as a
general one. #129 found that NumPy's `mean`/`std` reductions changed their last
bits between 2.2 and 2.3: the float32 `stack.std()` goes into the MRC header
RMS field, and the float64 `clean0.std()`/`.mean()` rescales the noise. It
replaces both with `math.fsum`-based reductions and regenerates the canonical
digests, with cross-version evidence for 1.26.4 / 2.2.6 / 2.4.1.

#129 and this branch share no files, so it merges cleanly, and once it lands
`CiFailClosedControls` should pass on SCARF here too.

The 24-movie run there (25.74 s, 0.90 GiB, compact arm) is a functional sanity
check on a different GPU model, not a timing result: one observation, and the
`gpu-devel` node was not exclusive.
