# Stage A / Stage B micro-plan (frozen before launch)

Admission: parent, "proceed bounded Stage A and B only". No Stage C, no M tier, no candidate K267/N/M producer, no timing or performance claim, no rebuild. Own writer of PR 289 only. `cpu64` is not used (PR290 owner, CPUs 32-47).

## Pins

| Item | Pin |
|---|---|
| Source under test | `96e7e7be0f08469da51c67a1ab251ae4e97cdfc3`; archive sha256 `313f671f4af90e227754ec17c6e8a9cae70a7ea5aaca713de62aa1d297b8ea36` (8497 files, no AppleDouble) |
| Current branch head | `544654d69704eb9222c98218afc740e140633db1`: differs from `96e7e7be` only under `docs/.../evidence/` (docs-only) |
| Engineering reuse of attempt 2 | tree ids identical at `94e39570` and `96e7e7be`: `src` `80cbd7a8df2e0d88b82cda0c855a6ea81f165565`, `tests` `fdedf1db39686588e219c8166526e5a92fc3372c`, `test-data` `8966e8cb8be1e473bc180a567df0e2860791b80b`, `CMakeLists.txt` blob `f9f5961222fc9afd5b55388496a0bc756ea17b15`. `tools` tree `b8137c41...` at `94e39570`, `c348042e4e1dd4e713aee5a56a2785ffeace7a13` at `96e7e7be` and at HEAD (the two files `ccf_dc_native_rows.py`, `test_ccf_dc_native_rows.py` differ). This is reuse of the build products, not a claim that the whole final source passed everything. |
| Binaries (attempt 2, no rebuild; re-hashed at launch and compared with the attempt-2 records) | `def` `2db45b2df8241e14bda28e9dbe3d7eae0ce9f5612a7b775bc33990aeb27bed6a`; `exp` `b918cadc571eb09d753fd454a20554400ea6443b6b0738e14670f96c7afb2857`; `iso` `3a7d4f472c0f795f6e3d7fdb7c31ab5c3e6bdef00ccf95d08a5cf5855155d0ff` (`/home/alex/mc-dcnative2-20261026/build-{def,exp,iso}/motioncorr`); oracle binaries `.../build-{exp,iso}/experiment_ccf_dc_stage` (hashes recorded at launch) |
| Tool commands | `stageAB/stageAB_chain.sh` sha256 `106e0231ddb8b3943854b1262ad4d8643b48f104ec6738fae7aed93a5298035d`; `stageAB/stageAB_check.py` sha256 `14169dfb51c27b03251d675cf5d7daff390d44de65809fcf1485f6ee4f3a54a3` |
| Interpreter | `/home/alex/.mc-venv/bin/python3` (attempt 2: CPython 3.12.3, NumPy 2.5.3; identity and module paths/hashes re-recorded at launch) |
| Device | GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, shared FOREIGN-CONTEXT correctness allocation (not exclusive, not timing, not science). Foreign `llama-server` PID 3983855 (user `dvi41342`) is never signalled, re-pinned or inspected beyond `ps`/`nvidia-smi` |

## Stage A (GPU hidden: `CUDA_VISIBLE_DEVICES=''`, `NVIDIA_VISIBLE_DEVICES=void`)

Exact final tools, staged from the pinned archive into `/home/alex/mc-dcnative-ab-20261026/src96e` and invoked by absolute path (the attempt-2 build trees' CTest files point at the older `94e39570` scripts and are not used; no `ctest`, so no claim is made for CTest at the final source):

1. `python3 src96e/tools/test_ccf_dc_native_rows.py -v` (pure; the native class skips by design).
2. `python3 src96e/tools/test_ccf_dc_native_rows.py --binary <attempt-2 exp motioncorr> -v` (`CcfDcRowsNative`, exp).
3. `python3 src96e/tools/test_ccf_dc_native_rows.py --iso --binary <attempt-2 iso motioncorr> -v` (`CcfDcRowsNative`, iso).

Required: the final line is `OK`; for runs 2-3 no skipped test; each of the listed tests reports `ok`, in particular the absent-tap, local-model, INVALID/PENDING/SCORED label, def-style, two-failed-runs, all-16-retained-rows and original-CLI tests (`stageAB_check.py unittest`). Also recorded: archive and tree proofs (`diff -rq` of `src`, `tests`, `test-data`, `CMakeLists.txt` between the attempt-2 tree and the staged `96e7e7be`), Python and NumPy versions, module paths and sha256 of the staged tools, venue K267 and N fixture MANIFEST and file hashes, stdout, stderr, exit codes. These are bounded reviewed consumer/CLI tests on CPU, not a K267/N campaign.

## Stage B (one shared GPU, existing oracle binaries, no rebuild)

For `exp` then `iso` (the unchanged oracle, as run by CTest, plus `--json`): `CUDA_VISIBLE_DEVICES=<GPU2 uuid> CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=2 taskset -c 80,81 .../experiment_ccf_dc_stage --json <out.json>`. The whole 16-test hardware matrix and the mutants are not rerun. A sampler (`nvidia-smi` GPU and compute-app queries every ~0.1 s) is started and confirmed ready (3 samples) before the oracle starts. Pre- and post-run GPU health and compute apps are captured.

Predeclared coverage: PASS needs all of (a) oracle rc 0, `ORACLE PASSED`, gates G1-G5 (and G6 for `iso`) with `failures == 0`, no fail, no inconclusive, pass counts > 0 in the JSON; (b) `cpu_global`, `cpu_local`, `cuda_single_global`, `cuda_single_local`, `cuda_batched_local` each with eligible frames strictly > 0; (c) the oracle's PID seen in the sampler holding a context on the granted GPU2 UUID and on no other GPU. A missing PID, a missing path or a sampler that was not ready is INCONCLUSIVE/UNRUN, never PASS, with no automatic retry.

## Guards and stop rules (checked before every step, no fallback or waiver)

- Leases, non-blocking: `motioncorr-dcnative-gpu2-cpu80-87` and `motioncorr-cuda-boundary-cpu80-87` for the window; `motioncorr-gpu2-correctness` before Stage B. Any busy lease stops the affected stage.
- Fresh GPU2 utilisation, memory and compute apps; fresh per-core busy% over 3 s for CPUs 80-87; processes running on those cores; free scratch and memory.
- STOP the affected stage if: any compute app other than PID 3983855 holds GPU2; GPU2 utilisation > 50 %; any core of 80-87 is > 50 % busy before the step; a lease is busy; a hash, archive or interpreter check fails. Stage A needs no GPU; Stage B stops without moving to another GPU.
- Caps: CPUs 80-87, `--j <= 8` (the pinned test commands), the oracle on two CPUs with OMP 2, scratch for the whole window <= 4 GiB combined (new extra <= 2 GB; attempt directories use 1.8 GiB), oracle memory < 2 GiB, no benchmark.

## Limits of the claims

The foreign context stays on GPU2 throughout; the oracle shares the device with it, so utilisation and any timing are not interpretable and are not claimed. A pass is a correctness window at the pinned binaries and source, not exclusive-GPU evidence, not a native K267/N result, not performance, not a whole-final-source CTest claim.
