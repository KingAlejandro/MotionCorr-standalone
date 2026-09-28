# Fixed-total-resource scaling experiment for static workers (#53 → #26)

Specification only. **Nothing here has been run, and no scaling result is claimed.**
It exists so the experiment is designed before compute is requested, not after.

Prerequisite: the integrated source (this port) is accepted. Prerequisite for the
GPU arms: an explicit coordinator allocation under the current #96/#66 rules.

## What the experiment has to separate

Adding a worker changes three things at once: the number of processes, the number
of GPUs, and — unless the CPU budget is held fixed — the aggregate number of
decoder threads. #53's own evidence says GPU-attributed time is ~1.1% of per-movie
wall, so a naive "2 workers are faster" result would most likely be measuring host
concurrency, not the second device.

The arms below hold the total CPU budget fixed and cross worker count against
aggregate decoder concurrency.

| Arm | Workers | `--j` / `--max_io_threads` per worker | CPU masks | Aggregate decode threads | GPUs |
|---|---|---|---|---|---|
| A1 | 1 | 16 / 16 | `96-111` | 16 | 1 |
| A2 | 2 | 8 / 8 | `96-103` ; `104-111` | 16 | 2 |
| B1 | 1 | 8 / 8 | `96-103` | 8 | 1 |
| B2 | 2 | 4 / 4 | `96-99` ; `100-103` | 8 | 2 |

A1↔A2 and B1↔B2 vary worker count at constant aggregate decode concurrency.
A1↔B1 and A2↔B2 vary decode concurrency at constant worker count.

**Recommended fifth arm, C2: 2 workers, j8/io8, masks `96-103` ; `104-111`, both
pinned to the same physical GPU UUID.** Without it, A1↔A2 confounds "a second GPU"
with "a second host process", and the experiment cannot attribute any gain to the
device. C2 costs one extra run and is the arm that answers #53's actual question.
Thread placement is a known large effect here, so every arm must record
`OMP_PROC_BIND`/`OMP_PLACES` as set, not as assumed.

Each arm runs the full 24-movie tutorial set, one arm at a time, under the single
benchmark mutex, with the box otherwise idle. Timings from arms run under
different occupancy are not comparable and must not be pooled.

## What must be recorded, per worker

| Quantity | Available today | Source / gap |
|---|---|---|
| GPU UUID | yes | `status.json` → `devices[k].uuid`; witnessed against `nvidia-smi --query-compute-apps=pid,gpu_uuid` samples |
| CPU mask | yes | `status.json` → `cpu_masks[k]`, and `command.json` per worker |
| movie ownership | yes | `shards/shard_manifest.json` → `shards[k].movies` |
| worker start/end | **no** | launcher records only aggregate `wall_seconds`; needs per-child start/end timestamps in `status.json` |
| per-movie start/end | **no** | needs a timestamped per-movie marker in the worker log, or `profile_cuda_movie.py` semantics extended to a multi-movie run |
| read/decode time | partial | per-movie stage lines exist in the worker log; `tools/profile_cuda_movie.py` parses them for a single-movie run only |
| H2D bytes / time | partial | CUDA build emits per-movie GPU markers; bytes are calculated from geometry, not measured — label accordingly |
| GPU compute intervals | partial | `cudaEvent` kernel totals exist (`src/acc/cuda/cuda_alignpatch.cu:339-441`); these are accumulated durations, not intervals, so they cannot show overlap or idle gaps |
| output / drain time | **no** | the per-movie tail (EPS/PDF/STAR writing, ghostscript spawns) is not separately attributed |
| final-worker tail / imbalance | derived | computable once per-worker start/end exist: `max(end) - min(end)` over workers, plus per-worker busy fraction |
| RSS | **no** | needs sampling of each worker PID's `/proc/<pid>/status` `VmHWM`; a shared-host `ps pcpu` average cannot see a burst |
| device memory | partial | `nvidia-smi` device-wide samples are supplementary, not per-process high-water marks; label as sampled |

Six of these are missing. **Do not run the matrix before they exist** — an arm that
cannot report per-worker start/end cannot report imbalance, which is one of the
five candidate explanations the experiment is meant to discriminate between.

The launcher is the right place for worker start/end, exit time and RSS sampling:
they are properties of the child processes it already owns, and adding them
changes no production source. Per-movie decode/compute/drain attribution belongs
with #74's profiling work, not here.

## What the result has to distinguish

Static workers may be limited by TIFF decode / CPU, storage, PCIe, GPU compute, or
load imbalance. Each has a signature in the table above:

- **decode / CPU** — B-arms slower than A-arms at equal worker count; per-worker
  decode time scales with `--j`.
- **storage** — aggregate read throughput flat across arms while decode time rises.
- **PCIe** — H2D time per byte rises when two workers transfer concurrently.
- **GPU compute** — accumulated kernel time is a material fraction of per-worker
  busy time. Current evidence says it is ~1%; a result contradicting that needs
  its own explanation.
- **imbalance** — `max(end) - min(end)` is a material fraction of arm wall time.

Equal-sized tutorial movies cannot expose stragglers. The #73 mixed real-movie
corpus is required before any imbalance conclusion generalises.

## Not in scope here

No dynamic coordinator and no persistent pull queue. Build one only if imbalance
turns out to materially limit throughput; a cost model (frame count × rendered
pixels plus measured codec cost, largest-first) is the cheaper first step, and
compressed file bytes are not a valid universal compute-cost proxy.

If a dynamic scheduler is later built: move movie descriptors, not decoded stacks;
bind each process to a GPU UUID; make ownership and retry idempotent; do not fork
after CUDA initialisation. Decode-thread and host/pinned-memory budgets must be
granted globally — two independently "bounded" workers can exceed the node budget
together.
