# Static multi-GPU whole-movie scheduling (#53), PR A

Design and changed-file whitelist: [`agents/designs/issue_53_multi_gpu_scheduling.md`](../../agents/designs/issue_53_multi_gpu_scheduling.md).

PR A refreshes the #53 launcher concept onto current main, makes the native
device-list behaviour honest, and proves the scheduling failure modes on CPU.
**It makes no throughput, memory or numerical claim**, and the native GPU
equality layer is prepared but unrun — see [`NEEDS_GPU.md`](NEEDS_GPU.md).

## What is here

| File | Role |
|---|---|
| `tools/multi_gpu/star_io.py` | STAR reader mirroring the C++ reader's observable semantics |
| `tools/multi_gpu/partition_star.py` | disjoint shards from original row bytes, with collision preflight |
| `tools/multi_gpu/run_multi_gpu.py` | one stock process per physical GPU, UUID-pinned, with device witnessing |
| `tools/multi_gpu/merge_workers.py` | staging plus lost/duplicate/misrouted/failed detection, deterministic order |
| `tools/multi_gpu/gpu_witness.py` | UUID selection and `nvidia-smi` compute-apps witnesses |
| `tools/multi_gpu/compare24.py` | per-movie exact comparison against a serial baseline |
| `tests/test_multi_gpu_scheduling.py` | 16 CPU-only cases, registered as the `MultiGpuScheduling` CTest |
| `tests/fake_worker.py` | binary stand-in with fault injection |
| `docs/multi_gpu/negative_controls.py` | 12 mutations, each required to break its case |

## Usage

```bash
# one worker per physical GPU, distinct output directories
python3 tools/multi_gpu/run_multi_gpu.py \
    --star movies.star --out run/ --binary build/motioncorr \
    --devices 0,1 --cpus 96-111 \
    -- --use_own --j 8 --dose_weighting --angpix 0.885

# stage, verify, and regenerate the dataset STAR with the stock binary
python3 tools/multi_gpu/merge_workers.py \
    --manifest run/shards/shard_manifest.json \
    --workers run/w0 run/w1 --status run/status.json \
    --out run/merged --report run/merge_report.json \
    --aggregate-with build/motioncorr --input-star movies.star \
    --aggregate-args -- --use_own --j 8 --dose_weighting --angpix 0.885
```

## Verified on CPU, 2026-09-28

Host `small-refmac-machine` (cpu64), cores 32-63 (NUMA node 1), under
`flock /tmp/motioncorr-issue96-cpu-validation.lock`. Raw logs in
[`pr_a_evidence/`](pr_a_evidence/).

- Build: `cmake -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF`, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`,
  g++ 13.3.0, cmake 4.4.3, Python 3.12.3.
- Source head `3eece28`; base `4c952b3f54479653512c4d208e09c9a8c02f3726`.
- Patched binary SHA-256 `f4748106a1a296efd961b655fce675c9336cda42ca63f7b4bf4488d12ef9e8f2`.
- Unpatched-main control binary SHA-256 `de35fddc37d8237576adea7d34bec618ce1bf4867286b87ec568815c71645f8a`.
- `tests/test_multi_gpu_scheduling.py --binary <built>`: **16/16 passed**.
- `docs/multi_gpu/negative_controls.py`: **12/12 mutations detected**, no survivors.
- `ctest --output-on-failure -j 4`: **14/14 passed** — the 13 pre-existing CPU tests
  plus `MultiGpuScheduling`. No pre-existing test changed.

**Recorded interference.** Two unrestricted `ctffind` process trees were running
throughout (PIDs 1156938/1156942 and 1635423/1635428/1635429, each
`OMP_NUM_THREADS=1 -j:1`), and host load average was 6.95–7.60. These are
correctness checks with no timing content, so the interference does not affect
any claim made here; it is recorded because the round requires it and because
nothing in this document may later be reused as a timing baseline.

## Device-list behaviour, before and after

Full transcript: [`pr_a_evidence/device_list_witness.txt`](pr_a_evidence/device_list_witness.txt).

| `--gpu` | unpatched main `4c952b3f` | this branch |
|---|---|---|
| `0:1:2:3` | generic "built without CUDA support" | names the 4 requested entries and refuses |
| `0,1` | generic | names the 2 requested entries and refuses |
| `0:1` | generic | names the 2 requested entries and refuses |
| `0abc` | generic | "not a non-negative device id" |
| `-1` | generic | "not a non-negative device id" |
| `0` | generic | generic — unchanged, correctly |

### What this evidence does and does not show

It shows that on a **CPU-only** build the list syntax is now rejected *as a list*,
with the requested count quoted back, where before it produced only the generic
missing-CUDA message. The syntax check was deliberately moved outside
`#if defined _CUDA_ENABLED` so this is observable without a GPU.

It does **not** show the behaviour this change actually exists to stop: on a
**CUDA** build, unpatched `--gpu 0:1:2:3` proceeds to `gpu_id = 0` and prints
`Using CUDA acceleration on GPU device 0`, running the whole dataset on one
device while the user asked for four. That is a code-reading claim
(`src/motioncorr_runner.cpp:257-259` at `4c952b3f`) plus an **unrun** witness
listed in [`NEEDS_GPU.md`](NEEDS_GPU.md). No CUDA build was made or run for PR A.

## Deliberate non-claims

- **No speedup, and no benchmark.** `run_multi_gpu.py` records a wall time for
  bookkeeping and says in its own status file that it is not a measurement.
  #26 owns this round's matrix. Historical four-GPU SCARF figures on source
  `0c7d68f` are not a current-main scaling curve and are not repeated here.
- **No `logfile.pdf` equivalence.** The PDF batch loop globs only the current
  pending list, so a partitioned or resumed run's PDF differs from a serial
  run's by construction. Nothing here produces one or compares one.
- **No numerical claim.** PR A changes no numerical result. The historical
  CPU/RELION Gate 2 failures and the noisy-truth characterisation failures are
  untouched and remain separate verdicts.
- **One worker per GPU is the first experiment**, not a claimed optimum, and
  whole-movie granularity is a scheduling decision, not a proof that intra-movie
  multi-GPU is impossible. That is deferred.
