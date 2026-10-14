# CPU local patch phase window experiment

Base: main `116eb04ad359cd5bf789b28809fc2047ea155b9b`. Issue #10.

## Scope and earlier work

The merged CUDA windowed patch spectra work in PR #168 already established the
same liveness observation. See `docs/perf_vram_tier1/report.md` and
`docs/vram_live_ranges.md`: local alignment consumes only the CCF support, with
full-patch frequency coordinates. This experiment applies that observation to
CPU phase updates. It does not change spectrum allocation, FFTs or CCFs.

For every iteration, CPU `alignPatch` builds `Fref` and each `Fccs` from precisely
`ccf_nfx` columns and `ccf_nfy` rows. Window row `wy` maps to full-spectrum row
`wy > ccf_nfy/2 ? wy-ccf_nfy+nfy : wy`. No other spectral bins are read during
alignment. Local `Fpatches` are cleared after shifts are interpolated and copied
into the polynomial model inputs. Grouped-frame patch spectra have the same
lifetime and support. Global `Fframes` are subsequently inverse transformed and
used for reconstruction, so their phase updates must remain full-sized.

## Change

The existing phase helper accepts optional window extents. Its default remains
the full geometry. Only `alignPatch(..., is_global=false)` passes the CCF window.
Table phases use the original signed full-spectrum row and the same normalized
shifts `-cur_xshifts/pnx`, `-cur_yshifts/pny`. The complex arithmetic and float
store retain their original expression order. The positive CCF Nyquist row stays
in the positive half, including odd half-sizes. Unconsumed bins remain at their
original values rather than receiving shifts; no caller may use them afterwards.

For a representative 768x742 patch and a 192x192 CCF, the complex pixel updates
drop from 385x742 = 285,670 to 97x192 = 18,624 per shifted group per iteration,
about 6.5% of the original. Trig table calls drop from 1,127 to 289. These are
operation counts, not measured stage or whole-movie speedups. Patch preparation,
CCF preparation, inverse FFTs, peak finding, and model fitting still run.

## Verification and timing protocol

`CpuPatchPhaseWindow` calls the production private helper through the existing
test friend and compares it with a frozen, licensed copy of the original full
helper. It checks 300 window geometries across odd and even full spectra, both
halves, crop edges, zero/partial/full extents and five successive phase updates.
Every retained complex float must match bit for bit, every discarded bin must
remain untouched. Default full geometry must match every original pixel.
GNU/ELF builds additionally wrap `sincos`/`sincosf` and check actual production
table call counts against window extents and full default geometry.

The same test compares actual production local and global `alignPatch` arms on
108 combinations of rectangular/even geometries, odd CCF half-sizes, 2/4/7 frame
groups with unequal amplitudes, j1/j4 and iteration limits 1/5, explicit CCF scales 0.7/1.0 and automatic
CCF sizing at scaled B=150. Convergence,
accumulated shift vector bits and iteration/RMSD logs must match exactly.

The separate unwrapped `cpu_patch_phase_bench --bench 1` (or `4`) times the
frozen original full-spectrum helper against the production window helper on
24 groups of a 768x742 patch,
20 updates per arm. Resetting and allocations of the frame stack are outside
the timer; per-call phase table allocations remain inside, as in production.
One warmup per arm is excluded. Six measured pairs alternate order. All retained
complex output bits are compared after every pair outside the timing interval. This is a
phase-helper experiment, not full patch alignment or whole-movie latency.

Release CPU build passed at `146dc07` with GCC 13.3.0, FFTW 3.3.10,
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`. Both focused CTests passed: the new
`CpuPatchPhaseWindow` matrix and the existing `PatchRetryState` control. The new
test took 4.41 seconds; this is test duration, not performance evidence.
Configure/build/test logs and binary hashes are in
`docs/cpu_local_phase_window_evidence/`.

## Measured container results

Published code `f627d5e0ff93c4abe1421ffbffcd450de389c797` also passed native
Linux CI #515: 53/53 CTests, known-motion/canonical/smoke/failure checks, and CUDA
compilation. No native GPU execution was performed. Raw CI logs are retained.

Measurements below ran only in container `442a2f5ea6ec`, with an 8-CPU quota and
8 GiB memory limit. j1 was pinned to CPU 0 and j4 to CPUs 0-3, with child-affinity
validation, identical explicit OpenMP settings, and the shared benchmark lock.
Other agents had released the measurement lane. Physical-host isolation is not
certified. The requested cpu64 VM was unreachable; after explicit authorization,
the container was used instead. These absolute times must not be compared to
cpu64 results.

For 460 phase-helper updates per arm, one excluded warmup per arm and six
alternating measured pairs:

- j1 frozen original full helper median **0.478413 s**, production window helper
  **0.035758 s**, a 13.38x ratio. Every pair favored the window helper.
- j4 full helper median **0.204968 s**, window helper **0.023017 s**, an 8.91x
  ratio. Every pair favored the window helper.
- Each of the 12 pairs compared all 446,976 retained complex output values bit
  for bit after timing; all matched. The baseline is the frozen original helper,
  compiled with the same flags, and the candidate calls production code.

These are within-process helper measurements. They do not establish a full patch
stage or whole-movie speedup. FFT preparation, CCFs and their inverse FFTs, peak
finding and model fitting remain unchanged.

All five actual main/candidate strict output-tree comparisons passed: small
512x512x16 global 1x1 and local 3x3 paths at j1/j4, plus a full tutorial 5x5 j4
pair with automatic CCF sizing, B=150, dose weighting, noDW and even/odd outputs.
There were no extra or missing artifacts in these pairs. The comparator checked
60 files, including 20 complete MRC files; it inventoried timing logs and PDFs
under its existing rules. All 30 canonical MRC/STAR file pairs have matching
normalized SHA-256 hashes in `canonical-products.json`. MRC normalization masks
only the known first-label writer timestamp; STAR normalization replaces each
tree's own output root.

The tutorial used `--group_frames 5`. Both movie logs record:

```text
Frame grouping: n_frames = 24, requested group size = 5
 | 1 2 3 4 5 | 6 7 8 9 10 11 | 12 13 14 15 16 17 | 18 19 20 21 22 23 24 |
```

Thus the actual four group sizes were 5, 6, 6 and 7. The small local patches have
full-size CCFs; the full tutorial and focused controls provide cropped-window
coverage.

The one tutorial pair had diagnostic wall times 56.607/40.609 s and peak RSS
4,556,152/4,554,328 KiB for main/candidate. One pair is insufficient for a movie
speed verdict, and the helper savings do not justify attributing that 16-second
gap to this change. No meaningful whole-movie RAM reduction is established.
No repetitions or artifacts were discarded, and no retry was performed.

Raw kernel pairs, commands, binary/input hashes, affinity probes, product
comparisons and movie logs are preserved under
`docs/cpu_local_phase_window_evidence/`. `summary.json` separates helper timings
from the single-pair diagnostic movie values. Combined performance with the other
CPU experiments is unmeasured.

## Prepared cpu64 driver

`docs/run_cpu_local_phase_window.py` remains portable to cpu64. Its default
`--expected-host small-refmac-machine` guard rejects any other hostname before
creating output or launching a child. Use the VM's exact hostname if it differs.
`--cpus-j1` and `--cpus-j4` accept taskset CPU lists containing exactly one or four
distinct CPUs, respectively. Choose those lists from the VM's topology so thread
placement matches the intended physical-core/NUMA comparison. Before each payload,
the driver runs a child affinity probe and requires the resulting CPU IDs to
match the requested list exactly. All arms share the same placement and OpenMP
settings, and the driver serializes with `/tmp/motioncorr-bench.lock`.

For example, on cpu64, with paths replaced by that VM's actual builds and data:

```sh
python3 docs/run_cpu_local_phase_window.py kernel \
  --base /path/to/main-build/motioncorr \
  --candidate /path/to/phase-window-build/motioncorr \
  --bench /path/to/phase-window-build/cpu_patch_phase_bench \
  --data /path/to/tutorial-data --out /path/to/new-phase-kernel-results \
  --expected-host small-refmac-machine --cpus-j1 0 --cpus-j4 0,2,4,6
```

The container runs explicitly passed `--expected-host 442a2f5ea6ec`; the portable
default remains cpu64. The other modes are `small-identity` and `tutorial-identity`. The latter runs one
strict main/candidate tutorial product pair with 5x5 patches, j4,
`--group_frames 5`, automatic CCF sizing at B=150, dose weighting, noDW and even/odd
outputs. The small mode covers global/local execution at j1/j4. The small local
patches have a full-size CCF, so the large tutorial pair and focused controls
provide the cropped-window coverage. Whole-movie wall values from these
single-pair controls are diagnostic only, not a speedup verdict. Hostname and
affinity checks alone do not certify exclusive ownership of the machine.
