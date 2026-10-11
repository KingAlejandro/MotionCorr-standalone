# Diagnostic file paths

Every per-worker log, timing record and memory record has its own path. None of
these names can be a movie product. In a worker directory the console log is
`launcher.console.log`, whose stem contains a `.` that `star_io.output_root`
never produces, so a top-level movie `run.tif` writes its own `run.log` beside
it without collision. `command.json` and `status.json` use an extension the
binary never writes. Fixed runner names (`corrected_micrographs`, `logfile`,
...) are refused at partition time.

`run_dataset.py --out D`:

| Path | Written by | Content |
|---|---|---|
| `D/dataset_status.json` | `run_dataset.py` | verdict, `dataset_ready`, `dataset_wall_s` (launch to publication), phase walls, input and binary sha256, `tree_rss` |
| `D/workers.log` | `run_dataset.py` | console of `run_multi_gpu.py` |
| `D/aggregate.log` | `run_dataset.py` | console of `merge_workers.py` |
| `D/aggregate.json` | `merge_workers.py --report` | merge verdict, `input_type`, `row_order`, joint-STAR problems |
| `D/workers/status.json` | `run_multi_gpu.py` | per-worker return code, CPU mask, device witness, `phases`, `rss_hwm_kib` with `rss_status`, and `phase_rollup` |
| `D/workers/shards/` | `partition_star.py` | shard STARs and `shard_manifest.json` |
| `D/workers/wK/launcher.console.log` | `run_multi_gpu.py` | worker K's stdout and stderr |
| `D/workers/wK/command.json` | `run_multi_gpu.py` | worker K's exact argv, environment and mask |
| `D/workers/wK/<movie root>.log` | the binary | per-movie log; the source of `binary_movie_wall_sum` |
| `D/merged/` | `merge_workers.py` | published products, joint STAR, `logfile.pdf` |
| `D/merged/_workers/wK/` | `merge_workers.py` | worker K's aggregates, tomography per-series tables, and its launcher files, staged so they cannot shadow the published ones |
| `D/merged/_workers/merge.log` | `merge_workers.py` | console of the `--aggregate_only` step |

Missing measurements are reported as missing, never as zero:

- `phases.binary_movie_wall_sum` is `null` when any assigned movie's log is
  absent or has no wall-time line; `phases.binary_movie_walls_missing` lists
  those movies.
- `rss_hwm_kib` is `null` with `rss_status: "MISSING"` and an `rss_note` when
  the high-water mark could not be read.
- `sampled_peak_gpu_memory_mib` in `D/workers/status.json` maps each device
  UUID to the largest per-process `used_gpu_memory` seen by the
  `nvidia-smi` witness sampler, or `null` if no sample saw that worker. It is a
  sampled lower bound, not a high-water mark; the binary's "Peak VRAM" log line
  is a calculated allocation, not a measurement.
- `phase_rollup` maxima exclude missing workers and count them in
  `n_workers_missing_setup` and `n_workers_missing_tail`;
  `first_product_spread` is `null` if any worker has no first product.
