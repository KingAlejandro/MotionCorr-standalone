# Stage A / Stage B result (one run, 2026-10-26 22:17:48Z - 22:18:34Z, 4GPUs)

Executed exactly as frozen in `MICROPLAN.md` (committed `b11c9baf` before launch). One run, no retry, no stop triggered. Raw logs, JSON and sampler files: `run1/` (1.2 MB; per-file sha256 in `run1/logs.sha256`); checker `stageAB_check.py`; offline re-parse `stageAB_reparse.py` with output `run1/reparse.out`.

## Pins as run

- Source `96e7e7be0f08469da51c67a1ab251ae4e97cdfc3`, archive sha256 `313f671f4af90e227754ec17c6e8a9cae70a7ea5aaca713de62aa1d297b8ea36` (verified on the venue; 8497 files extracted, no AppleDouble). Branch head at launch `b11c9baf` (docs-only above `96e7e7be`).
- Tree proof on the venue: `diff -rq` between the attempt-2 tree (`94e39570`) and the staged `96e7e7be` for `src`, `tests`, `test-data` and `CMakeLists.txt` found no difference except attempt-2 `__pycache__` directories; the tools that differ are exactly `ccf_dc_native_rows.py` and `test_ccf_dc_native_rows.py`.
- Binaries (re-hashed, each equal to its attempt-2 record): `def` `2db45b2d...`, `exp` `b918cadc...`, `iso` `3a7d4f47...` (full values in `MICROPLAN.md`). Oracle binaries: `exp` `3b93be6a06a5a6c41148671bdb654e1a4b33ad500f49e601a451e36e3c95b026`, `iso` `99f1f35228681ea60836094d300237020b89a806ab5a5ebdd872f8b1cc3dfdb5` (`/home/alex/mc-dcnative2-20261026/build-{exp,iso}/experiment_ccf_dc_stage`). No rebuild.
- Interpreter: `/home/alex/.mc-venv/bin/python3` = CPython 3.12.3, NumPy 2.5.3 (`.../site-packages/numpy/__init__.py`), Linux 6.8.0-136, glibc 2.39. Imported tool modules came from `/home/alex/mc-dcnative-ab-20261026/src96e/...` (sha256 of `ccf_dc_native_rows.py` `569c33a1...`, `ccf_dc_tap_field.py` `831ba828...`, `check_motion_diagnostics.py` `2be34b82...`, `check_realistic_motion.py` `b0ab099a...`, `motion_field.py` `d72cfad7...`, `generate_ccf_dc_n_controls.py` `8e5a6f58...`, `generate_motion_diagnostics.py` `5e781bb2...`); no attempt-2 path was on `sys.path`.
- Venue fixture hashes (regenerated with the venue interpreter, all files in `run1/logs/input-hashes.sha256`): K267 `MANIFEST.json` `9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc` (equals the retained #267 manifest's sha256 recorded in the earlier native_v2 index); N controls `MANIFEST.json` `6e7b19bd4d5be963c51813e7941749daeb1ca44f8825e79f4df623676fd7c2a8`. The N files were also checked byte for byte against the retained render report pins by `test_n_control_generator` inside Stage A.
- Leases (non-blocking, all acquired, released at exit): `motioncorr-dcnative-gpu2-cpu80-87` and `motioncorr-cuda-boundary-cpu80-87` at 22:17:48Z; `motioncorr-gpu2-correctness` at 22:18:12Z.

## Stage A (GPU hidden: `CUDA_VISIBLE_DEVICES=''`, `NVIDIA_VISIBLE_DEVICES=void`; absolute paths into the staged `96e7e7be` tools, no `ctest`)

| Run | Command (`run1/logs/A-*.cmd`) | Exit | Result |
|---|---|---|---|
| pure | `test_ccf_dc_native_rows.py -v` | 0 | 28 tests, `OK (skipped=17)`: the 17 native tests skip by design with no binary; the 11 pure tests `ok` |
| exp | `... --binary <attempt-2 exp motioncorr> -v` | 0 | 28 tests, `OK`, 0 skipped, 28 `ok` |
| iso | `... --iso --binary <attempt-2 iso motioncorr> -v` | 0 | 28 tests, `OK`, 0 skipped, 28 `ok` |

Required tests all `ok` in the native runs (absent-tap fail-closed, N tap with a local model, INVALID/PENDING/SCORED labels, def-build STAR-only row, two failed runs are not an identity, global-only row cannot claim local coverage, `--skip_logfile` leaves products identical, N row, identity report, failed exit not rescued by a tap, placeholder tap, all 16 retained rows, percentile over the dense ROI, witness selectivity on every reached site, N-control generator pins, thread pins, original K267 CLI). Checker limitation, kept visible: the first checker's one-line regex reported `test_n_score_reproduces_all_16_retained_rows` as "not ok" because that test has a docstring, and `unittest -v` then prints its result on the next line; the raw logs show `... ok` for it in all three runs and `stageAB_reparse.py` (offline, run after the fact) confirms every required test `ok` with 0 skipped in the native runs. The original `A-*.check` files are kept as produced.

These are bounded consumer/CLI tests on CPU with real tiny runs of the pinned commands (K267 `affine`/`zero`, N `vel0_N5`); they are not the K267/N campaign.

## Stage B (existing oracle binaries, GPU2 shared with the foreign context)

Command per build (`run1/logs/B-*.cmd`): `CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=2 taskset -c 80,81 <oracle> --json <out.json>`; the sampler was confirmed ready (3 samples) before the oracle started.

| | `exp` oracle (pid 4010143) | `iso` oracle (pid 4010509) |
|---|---|---|
| Exit / output | rc 0, `ORACLE PASSED` | rc 0, `ORACLE PASSED` |
| Gates (pass counts; fail 0, inconclusive 0) | G1 1100, G2 65, G3 240, G4 600, G5 80 | G1 1100, G2 65, G3 240, G4 600, G5 80, G6 3 |
| Eligible frames, `cpu_global` / `cpu_local` | 1536 / 1536 | 1616 / 1536 |
| `cuda_single_global` / `cuda_single_local` / `cuda_batched_local` | 1496 / 1496 / 2992 | 1596 / 1496 / 2992 |
| Zeroed frames (same order) | 780 / 780 / 780 / 780 / 1560 for cpu_global, cpu_local, cuda_single_global, cuda_single_local, cuda_batched_local | 830 / 780 / 830 / 780 / 1560 |
| Device witness | sampler 26 samples; PID seen holding a context on GPU2 only (19 samples) | 34 samples; PID on GPU2 only (26 samples) |
| GPU2 during the run | max util 13 %, max memory 863 MiB (foreign 414 MiB + oracle) | max util 13 %, max memory 859 MiB |

Predeclared coverage (a), (b), (c) all met: `WITNESSED`, `ALL_PATHS_STRICTLY_POSITIVE`, `GATES_ALL_PASS_NONEMPTY`. Pre/post GPU health (`B-*.health.pre/post`): GPU2 31 C, 62.6 W, P0, clocks-event reasons `0x0` before and after both runs; compute apps before and after: only the foreign PID 3983855. The sampler also saw the foreign process on all four GPUs throughout; GPU3 stayed at 87 % utilisation under it (not used by us).

## Guards, resources, deviations

- Guards (before every step): other GPU2 compute app none; GPU2 utilisation 0 % before each oracle; cores 80-87 0 % busy at every guard; scratch 316 MB new for the window (the two earlier attempt directories use 1.8 GiB, combined about 2.2 GiB, below the 4 GiB cap); memory 417 GiB available; oracle memory about 450 MiB.
- CPU caps respected: the window ran under `taskset -c 80-87`; the oracle on two CPUs with `OMP_NUM_THREADS=2`; the pinned test commands use `--j 8`/`--j 2` inside the eight assigned CPUs.
- No STOP, no retry, no fallback, no signal to or inspection of PID 3983855 beyond `nvidia-smi`/`ps` (and its CPU effect, not visible on 80-87).
- Deviations from a literal reading: the oracle was run with an added `--json <path>` (needed for the per-path table; the gate logic is unchanged); the checker limitation above; Stage A did not use `ctest` (no claim of CTest at the final source).

## Claim limits

A correctness window at the pinned source and binaries on a GPU shared with a foreign context. Not exclusive-GPU evidence, not timing or performance, not a K267/N result, and not "every test passes on the whole final source": attempt 2 (source `94e39570`) is reused for the build products and the rest of the CTest set on the engineering ground that the compiled inputs are identical.

## Proposed frozen Stage C (HELD; for the parent's specific release only)

- Source `96e7e7be`, archive `313f671f...`; binaries `def` `2db45b2d...`, `exp` `b918cadc...`, `iso` `3a7d4f47...`; GPU2 UUID `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598` shared with the foreign context (same guards and stop rules as above, re-checked before every producer); CPUs 80-87; fixtures: K267 manifest `9697c203...`, N manifest `6e7b19bd...` (regenerated, hashes in `run1/logs/input-hashes.sha256`).
- Ledger: `ledger.csv`, 176 jobs of which Stage C would be the 160 K267 and N jobs: 80 CPU-backend (K 48 + N 32; no GPU) and 80 CUDA-backend (K 48 + N 32); the 16 M jobs stay HELD. The 96 comparison pairs of those rows (K 32 + N 64; the 16 M pairs excluded) and the 16 C-REPRO rows (`repro.csv`) are evaluated from those results. Gates: B3 (48 rows), B4 (12 rows, run first), SEL (52 rows).
- Commands: `k267_argv` (original per-case grid; `--j 8`, OMP 8) and `n_argv` (`--j 2`, OMP 2), environment from `run_env`; arms as the ledger; `arm unset` rows without report/tap on `exp`, `def` rows without report/tap.
- Order: CPU-backend rows first (no GPU), then B4, then the remaining CUDA rows; one producer at a time; per-row run directory with `argv.json`, `rc.txt`, `stdout.txt`, `stderr.txt`, `witness.json`, `tap.json`, outputs; every row graded by `ccf_dc_native_rows.py`; field FAIL/UNIDENTIFIABLE and INCONCLUSIVE kept as results.
- Not yet existing: the Stage C harness (driver that runs the ledger under the guards, writes the run directories and calls the graders). It would be written, tested locally and put through review before any release. No Stage C row has run.
