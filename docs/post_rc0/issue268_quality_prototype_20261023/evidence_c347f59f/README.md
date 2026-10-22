# #268 quality-report prototype — CPU evidence at `c347f59f`

**Result:** on Linux CPU, all eight frozen rows (E1–E8) and all five checker
negative controls (N1–N5) PASS (`remote/campaign/results.json`). The
default-OFF flag-rejection probe is INCONCLUSIVE (defective probe, see below).
Every CUDA row is UNRUN. This is evidence for an experimental observation
prototype, not M4 adoption, not an approved schema and not an accuracy result.

## Identity

| Item | Value |
| --- | --- |
| Experiment source | `c347f59f25a2148642130136c6462491c8db36d1`, tree `9a11f683…`, clean |
| Base (B0) source | `bbf24607dec537bd13351f061047ea38bd38237b` (production source = C1 `e77a51a2`), tree `ff2495b7…`, clean |
| Design/protocol frozen | `5f2ca4b8`; amendments A1/A2 committed in `c347f59f`, before the remote run |
| Host / CPU | `4-gpu-vm`; builds `taskset -c 14-15 -j2`; every MotionCorr process `taskset -c 14`, `OMP_NUM_THREADS=1`, `--j 1` |
| Admission | guard 3315461/3315463 absent; guard264 and i61 cpu14-15 lane locks unheld (`/proc/locks`); own lease `/tmp/motioncorr-q268-cpu14-15.lock` held by the driver; shared build lock taken nonblocking per build |
| Compiler | `/usr/bin/c++` (GCC 13), Release `-O3 -DNDEBUG` |
| B0 `motioncorr` | `4ffbba06b4a990a2f7696cf0e8a71b48fe72c0d0e124dc52282f3facab7eb80c` |
| B1 (exp, option OFF) | `64069712f9e7eff67dd091f6289b76e2c62a60c8468b5a558c4dcf64cf6b77be` |
| B2 (exp, option ON) | `3693e2e9691052dc981b1c8f5ae9f1185ef48616fead31a1b75bac61a1fc065a` |
| B3 (exp, ON + CUDA, compile only, never run) | `a0708efb1894ce982a0d8fc67a59b6830a0ef128ad7d806694fb531bcb496a1d` |
| Inputs | `test-data/generate_motion_diagnostics.py` at the experiment head; all case files equal `GENERATION_RECORD.json` (checked by the harness before any run; hashes in `remote/campaign/manifest.json`) |
| Scratch | `/mnt/clathrin/alex-motioncorr-q268-quality-20261023-c347f59f`, 533 MiB of the 8 GiB cap |
| Driver | `remote/driver.sh` (sha256 `6499b29c…`), PID 3324419, start 2026-10-22T23:31:05Z, exit 0 at 23:39:42Z; no GPU process, no `nvidia-smi` |

The ON-build sidecars record `configured_source_revision` `c347f59f…`, dirty
`false`, and `binary_sha256` equal to B2's hash.

Native MotionCorr processes: 16 (P1–P14, plus two parse-only flag probes).

## Rows

| Row | Verdict | Key observation |
| --- | --- | --- |
| E1 default-off neutrality (B1 and B2 without flag vs B0) | PASS | products identical, exits 0, no quality files |
| E2 report-on vs B0, six movies 3×3 | PASS | products identical; every sidecar's global and per-patch iterations, final RMSD and state agree with the solver's printed RMSD; aggregate counts agree |
| E3 forced `--max_iter 1`, affine | PASS | global `iteration_limit` (1 iteration); 4/9 patches converged, 5 dropped, model retained (20 observations, just above the existing > 18 requirement) |
| E4 product write failure (integer `.mrc` path is a directory) | PASS | B0 and B2 both exit 1; zero `published`, integer `failed`/`product_write_failed`; aggregate `withheld_movie_failures` |
| E5 sidecar write failure | PASS | exit 0, products identical; flat sidecar absent and recorded as a write failure; `quality_evidence_complete=false` |
| E6 aggregate write failure | PASS | exit 0, products identical, six sidecars, stderr warning, no aggregate |
| E7 old/missing/stale sidecar resume | PASS | P11 and P12 joint STAR and all products identical; sources missing/missing/stale/resumed/resumed/this_run as frozen |
| E8 too-few-observations fallback (integer, forced `--max_iter 1`) | PASS | 0/9 patches converged, `global_only`/`too_few_converged_observations`, no local model block; products identical |
| N1–N5 checker negative controls | PASS | each tampered copy is rejected |
| B0/B1 reject `--experimental_quality_report` | INCONCLUSIVE | both probes exited 1 on the earlier "choose MotionCor2 or own implementation" check, before unknown-option parsing; not rerun (process cap reached). Default-off neutrality rests on E1 |

E2 actual global states: zero, affine, flat `converged`; integer, fractional,
noisy `iteration_limit` (integer final RMSD 0.923235 px, as in #273's CPU
record). They match the frozen prediction. All six movies retain a local model
with 9/9 converged patches on this host. Flat converges and still reports
`motion_identifiability` and `peak_validity` as `not_assessed`.

## Development runs (not evidence)

`local_dev/` holds the Mac (arm64, Apple clang) development runs of the same
harness. They found two harness/protocol problems that were fixed before the
remote run: a checker crash on a missing product (fixed to reject) and the E5
product-hash expectation (amendment A2). On the Mac, integer and noisy dropped
1 and 2 patches under default settings (retained model), unlike Linux. The Mac
probe that selected the E8 fixture is described in PROTOCOL.md amendment A1.

## Limitations

- CUDA: global resident/streaming, batched, per-patch device, same-input retry
  and device-preparation-decline recording are compiled (B3, `motioncorr`
  target only) and never executed. No CUDA test target was built.
- Not exercised: `distortion_guard_rejected`, `fit_rmsd_above_threshold`,
  `operator_error`, `not_run`, `sidecar_invalid`, a same-input retry, and
  retained e10216-01 at the default five iterations. Forced `--max_iter 1` rows
  are not evidence about the default case.
- Dataset/multi-GPU aggregation, tomography and `--aggregate_only` are not
  implemented. The aggregate covers one process's output directory.
- Identifiability and peak validity are never assessed.
- MRC creation time is masked in product comparison (first header label only).
- No timing claim.
