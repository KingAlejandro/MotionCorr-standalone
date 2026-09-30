# Compact-ingest support matrix: raw evidence

Produced by `tests/run_compact_ingest_support_matrix.py`. The readable result is
[`../SUPPORT_MATRIX.md`](../SUPPORT_MATRIX.md); this directory holds what it
rests on.

- `scarf-3514089/` — run of record. SCARF `gn0003`, Slurm job 3514089, one
  cgroup-isolated A100-SXM4-40GB (`GPU-6ddab9a9-…`), CPU mask 5-8,37-40.
- `scarf-3514082/` — an earlier complete 16/16 run of the same matrix on
  `gn0001` and a different device, before the gain-effect control was added.
  Retained as a second SCARF execution, not as the run of record.
  Each `support-matrix.json` carries every arm's command line, PID, start ticks,
  executable link, CPU mask, sampled `nvidia-smi` compute-app UUIDs, input and
  binary hashes, the per-movie native-stage verdicts, the validated manifest and
  every product's header/extended/payload sha256 and its dmin/dmax/dmean/rms. `compute-apps-{before,after}.csv`
  show the device idle either side of the run. The binary came from Slurm build
  job 3514047 (`build-slurm-3514047.out`, `build-binaries.sha256`).
- `vm-4gpu/` — the same 16 rows on a second host with a different A100 variant,
  driver and independently built binary, plus the CUDA CTest log (29 collected).
- `cpu64/` — the 22-test required CPU suite from a clean clone of the branch
  head, with its collection validation.

Every `support-matrix.json` is self-describing: `summary` gives the verdict,
`cases[].status` the per-row verdict, and `cases[].witnesses` the per-movie
native-stage booleans. A row with `status: PASS` and an empty `witnesses` block
is impossible — the witness assertions raise before a row can pass.

These are same-backend results on one device per venue. They are not CPU/CUDA
agreement, not motion truth, and not scientific validation.
