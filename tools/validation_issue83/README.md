# Issue 83 validation harness

Validates the **declared** native CUDA support matrix and the repeat / batch /
non-prefix-resume equality required by issue #83. Tooling only: nothing here
touches production sources, CMake, the CUDA backend or the runner.

## What it does and does not decide

This harness decides **implementation coverage**: did the configuration run
natively on CUDA, did it produce the complete declared product set with readable
headers and original-pixel metadata, and is every movie byte-identical across
schedules.

It does **not** define any numerical acceptance criterion. Pixel and trajectory
equality is delegated to `tools/compare_motioncorr.py --gate exact` as a
subprocess, and motion accuracy to `tools/run_known_motion_gates.py`. Their
thresholds, profiles and verdicts are used exactly as merged.

Numerical gates and CPU-agreement diagnostics are reported as **separate
verdicts**. A row passing here never converts a historical CPU/RELION Gate 2
failure into a pass.

## Files

| File | Purpose |
|---|---|
| `matrix.py` | Declares the bounded rows and their required products. No thresholds. |
| `products.py` | Output inventory, MRC header/payload consistency, movie STAR unit checks. |
| `run_matrix.py` | Executes each row's schedules and records raw per-case verdicts. |
| `run_all24_schedules.py` | All-24 tutorial repeat/batch/non-prefix-resume equality. |
| `report.py` | Renders the compact support table; names unrun rows. |

## Replay

Fixtures are generated, not committed:

```sh
python3 test-data/generate_known_motion_fixture.py --outdir <FIX> --include-heavy
```

Small matrix on a CUDA device:

```sh
python3 tools/validation_issue83/run_matrix.py \
    --binary build-cuda/motioncorr --gpu 0 \
    --fixtures-dir <FIX> --outdir evidence/matrix \
    --json evidence/matrix/summary.json
```

All-24 tutorial schedules:

```sh
python3 tools/validation_issue83/run_all24_schedules.py \
    --binary build-cuda/motioncorr --gpu 0 \
    --runroot <RUNROOT> --outdir evidence/all24 \
    --json evidence/all24/summary.json
```

Compact report:

```sh
python3 tools/validation_issue83/report.py \
    --matrix-json evidence/matrix/summary.json \
    --all24-json evidence/all24/summary.json \
    --truth-json evidence/truth/summary.json \
    --out docs/issue83/support-report.md
```

`run_matrix.py` and `run_all24_schedules.py` exit nonzero whenever any declared
row is unrun, any movie is missing its image/metadata pair, or any comparison
fails. Exit zero is a necessary but not sufficient condition: the raw JSON
carries the per-movie verdicts the report is built from.

## Deliberate exclusions

- EER and compressed decoding paths: issue #8.
- Broad allocation/plan/execution fault injection: issue #69.
- Multi-GPU sharding: issues #53 / #55; consumed only once its aggregation is
  independently valid.
- Optional CUDA event profiling: issue #74.
- Early-versus-late binning is never compared as an exact oracle (#68): each
  binning mode is only compared against itself across schedules.
