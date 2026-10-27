# Response to round-3 review (`ROUND3_REPORT.md`, sha256 `75de3fba78716b04ea6c8f45442dd9d668c4473058cf8b80aba844cd61030b43`)

Round 3 cleared `ad87df9e` with no BLOCK or MATERIAL finding. The two optional LOW items are fixed in one small tools/tests commit; production `src/` is unchanged since `b75039a0`.

| Item | Response | Test |
|---|---|---|
| N tap with `local_enabled=true` or nonzero coefficients scored SCORED although the run is global-only | `grade_n` refuses it: INVALID, "tap reports a local model but the N control is global-only". Nonzero coefficients with the flag off were already refused by the bridge. | `test_n_tap_with_a_local_model_is_invalid` |
| `runtime_representation: SCORED` stayed on INVALID tap rows | The field is `PENDING` while the tap is being checked, `SCORED` only on success, `INVALID` on every tap/bridge/STAR-readback failure, `NOT_REQUESTED` for declared def-build rows. | `test_invalid_tap_rows_are_not_labelled_scored` |

Venue run script (outside Git, retained in `evidence/venue_attempt3/` with its logs): full `ctest -V` stdout and the exact command per build; interpreter and NumPy identity; fixtures regenerated with the venue interpreter and hashed; for `exp` and `iso` the oracle is also run directly with `--json` while `nvidia-smi --query-compute-apps` is sampled, and `oracle_paths.py` requires `cpu_*`, `cuda_single_global`, `cuda_single_local` and `cuda_batched_local` to each have eligible frames > 0 so a no-device or skipped CUDA branch cannot read as a pass (checked locally against a CPU-only oracle JSON: it prints `PATH_NOT_REACHED`, exit 1). Attempt 1 (source `b75039a0`) and attempt 2 (source `94e39570`) are separate evidence directories and are not upgraded.
