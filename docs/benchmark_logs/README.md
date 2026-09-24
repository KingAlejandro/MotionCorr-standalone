# Benchmark logs

`standalone_j1.log` and `standalone_j4.log` are from the original 2026-09-23 run before the defect-correction determinism fix. The four configurations in that run overlapped in time, so those standalone logs are retained only as historical evidence.

`relion51_j1.log` and `relion51_j4.log` are the completed RELION 5.1 comparator runs. Their output artifacts were reused for the fixed-code comparison after checking the input data, run options, process exit status, and output files.

`standalone_j{1,4}_chunk_{0..5}.log` are the 2026-09-24 fixed-code rerun. Each setting processed the same 24 movies as six sequential four-movie batches with `--seed 1`; the two settings did not overlap. `timing_j{1,4}_rep{1..3}.log` are separate, sequential repeats of the first movie for a warm-run timing check.

See [the validation report](../spa_24_movies_validation.md) and [machine-readable manifest](../spa_24_movies_manifest.json) for the complete gate results and provenance.
