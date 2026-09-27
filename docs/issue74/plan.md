# Issue 74 — Optional CUDA profiling overhead: measurement plan

Companion to `audit.md` (which classifies the events) and `issue74_gpu.sbatch`
(which is the plan, executable). This file says what would make the result
believable and what would make it worthless.

## What is being measured

A runtime switch, `RELION_CUDA_DETAILED_PROFILE`, makes the profiling-only CUDA
event pairs and their `cudaEventSynchronize` calls optional. Default is **on**,
i.e. exactly the behaviour merged in #82; a CPU-only CTest
(`CudaProfilePolicyDefault`) pins that default so it cannot drift silently.

Three arms:

| arm | binary | environment |
|---|---|---|
| `base` | built from `1d7e13f` (pre-change) | — |
| `cand-on` | built from the issue-74 branch | unset (default) |
| `cand-off` | **the same bytes as `cand-on`** | `RELION_CUDA_DETAILED_PROFILE=0` |

The switch is runtime rather than build-time for one reason: `cand-on` and
`cand-off` must be the same binary, so that codegen, inlining and register
allocation cannot be confounders in the A/B. `base` exists separately to show
that `cand-on` reproduces pre-change behaviour.

## Controls

* **One allocation.** Everything — both builds, all runs, all comparisons — runs
  inside a single `--exclusive` single-node GPU allocation, so source, compiler,
  CUDA 12.8 toolkit, device, build options, staged inputs and filesystem cache
  are common to every arm. Inputs are staged to node-local `/tmp` and hashed.
* **Separate node from other threads.** `--constraint=scarf23` targets
  `gn3000-3002`; the concurrently running sibling GPU job sits on `gn0005`
  (`scarf21`). Different physical node, different GPU, no shared benchmark.
* **No #85 I/O branch.** The baseline arm is `1d7e13f`, not #85's changed I/O
  branch, so I/O work cannot leak into this attribution.
* **Interleaving.** Timing is three `ABBA` blocks (12 runs, 6 per arm) so that
  linear drift in node state cancels rather than loading onto one arm. The
  `base` binary is timed at the end as a cross-version check.
* **Every timing run is hashed.** A run whose trajectories differ cannot be
  silently counted as a clean timing sample.

## Correctness must be settled before any timing claim

Gate C (`compare24.py` → `tools/compare_motioncorr.py --gate exact`) compares
MRC pixels, MRC headers and per-movie STAR trajectories, fails closed, and is
run five ways: each arm against the merged reference, `cand-off` against
`cand-on`, and `cand-on` against `base`.

Gate C does not read everything a movie emits, so `compare_aux_outputs.py`
covers the rest of the per-movie output array: `corrected_micrographs.star`,
the 24 `_shifts.eps` trajectories, and every line of all 24 logs except the ones
that are durations or the profile-mode line itself. That means hot-pixel counts,
per-iteration RMSD, patch geometry, polynomial fit RMSD and the
`[CUDA Global Alignment] completed; converged=` marker are all required to be
byte-identical between `cand-on` and `cand-off`.

`run_known_motion_gates.py --include-heavy` is run in both modes for the
global / local / DW / real-scale fixtures.

## Execution witness, and why compile-only evidence is not enough

The claim at risk is "profiling off still runs on the GPU". The merged markers
already answer it and are reused unchanged: a stdout startup marker and a
per-movie log completion marker, both outside the profile block. The job asserts
`startup >= 1` and `completion == 24/24` for **every** arm including `cand-off`.

`run_known_motion_gates.py` is run once more with no `--gpu`, where
`backend_evidence()` *rejects* any run showing CUDA markers. A pass there is what
makes the marker a witness rather than a string: it shows the markers are not
satisfiable by a CPU run. Neither a successful compile nor a zero exit status is
accepted as evidence of native CUDA execution anywhere in this plan.

## What counts as a benefit

The unit is **process wall time and process maximum RSS**, from
`/usr/bin/time -v`, over the whole 24-movie run. Event-level kernel timings are
explicitly *not* the metric: removing the events removes the very instrument
that would report them, so an improvement in reported kernel time would be
circular. GPU memory is sampled with `nvidia-smi` for one pair.

Variability is reported as the spread over the 6 runs per arm, not as a single
best-of. The prior full run cost ≈30.17 s wall / ≈1.63 GiB max RSS, so the
profiling-only synchronizations (≈`5 × iterations` per alignment call, 26 calls
per movie, plus 72 per movie in dose weighting) have to be worth a visible
fraction of ~30 s to matter at all.

**A negligible or negative result is an acceptable outcome and will be reported
as such.** If the measured wall-time difference does not clear the run-to-run
spread, the recommendation is to keep the default at `on` and keep the switch
only if it pays for itself; if it does not, saying so is the deliverable.

## Default policy

The default is not changed by this branch, and no default change will be
recommended before the exactness gates above have passed on the all-24 tutorial
case and the representative global/local/DW fixtures.

## Status

Written before the run. Results and the pass/fail/unrun verdict go in
`results.md`; raw evidence lands under `docs/issue74/evidence/`.
