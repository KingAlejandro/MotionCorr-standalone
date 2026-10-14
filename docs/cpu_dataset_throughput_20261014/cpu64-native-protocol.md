# Native cpu64 throughput protocol

This is the separate 64-core VM protocol. Container diagnostic results must not
be pooled with this venue. Remote access is currently unavailable from this session, so this
native protocol is **unrun**. Require observed
`hostname -s` to equal `small-refmac-machine` before building or running payloads.
The archived container's 8 GiB preflight says nothing about this VM's capacity.

## Freeze the allocation before choosing layouts

1. Read current CPU allocation, topology and NUMA nodes (`lscpu -e`, process
   affinity, `numactl --hardware`), available RAM and cgroup CPU/memory limits.
   Inspect existing jobs and their CPU/memory use; leave unrelated work alone.
   Historical core masks and the VM's advertised 64 cores are not an allocation.
2. Coordinate with the active #180 owner and other workers. Confirm the actual
   shared benchmark lock and permitted masks. Historical CPU validation used
   `/tmp/motioncorr-issue96-cpu-validation.lock`; do not assume a new private
   lock serializes current work. Inspect occupancy again **after acquiring the
   confirmed shared lock**, and finish all builds/tests before timing.
3. Select one fixed union of idle permitted CPU IDs and an explicit RAM budget
   that leaves headroom for existing work, launchers and report generation.
   Calibrate peak memory for the exact movie/product mode before increasing
   worker count. A skipped layout is retained, never forced into an OOM.
4. Start within one observed NUMA node where possible. Hold the CPU-ID union,
   memory policy and OpenMP policy fixed across process layouts. Record actual
   worker affinity and sampled page placement; a `numactl` argument alone is
   not a residency witness. Cross-node placement is a separate matched series.

An illustrative 16-CPU series is 1x16, 2x8, 4x4 and 8x2. Use it only when that
budget is actually allocated. Every layout must partition the **same CPU IDs**
into disjoint masks, with `--j` equal to each mask's width. Do not give several
workers the same OpenMP place list without disjoint process affinity.

## Run the existing native publication endpoint

Use `tools/multi_gpu/run_dataset.py`, not the diagnostic fallback. The following
is a single-layout template; all `CPU64_*` values must be populated from the
confirmed allocation and frozen manifest. `CPU64_LAUNCHER_ARGS` contains CPU
worker count, disjoint masks, fixed union budget and matching OpenMP settings,
for example `--workers 2 --no-witness --cpus '32-39;40-47' --cpu-budget 16
--worker-extra='--j 8' --worker-extra='--j 8' --omp-proc-bind close --omp-places
cores` **only if that exact allocation was
observed and approved by the coordinator**. Use a fresh output for every arm.
Keep common `--j` equal to the fixed aggregate budget so report publication has
the same setting across layouts; repeat `--worker-extra` once per worker to
override its movie thread count to its mask width. The launcher also sets each
worker's `OMP_NUM_THREADS` from that width.

```sh
test "$(hostname -s)" = small-refmac-machine
exec 9>"$CPU64_SHARED_LOCK"
flock 9
# Inspect current occupancy again while holding this shared lock.
numactl --physcpubind="$CPU64_CPU_UNION" --membind="$CPU64_MEM_NODES" \
  env OMP_DYNAMIC=FALSE OMP_WAIT_POLICY=PASSIVE OPENBLAS_NUM_THREADS=1 \
      MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  python3 tools/multi_gpu/run_dataset.py \
    --binary "$CPU64_BINARY" --star "$CPU64_STAR" --out "$CPU64_FRESH_OUT" \
    --launcher-args "$CPU64_LAUNCHER_ARGS" \
    --required-products '.mrc,.star,_noDW.mrc,_EVN.mrc,_ODD.mrc,_shifts.eps' \
    -- --use_own --j "$CPU64_CPU_BUDGET" --seed 1 \
       --angpix 0.885 --voltage 300 --bfactor 150 --patch_x 5 --patch_y 5 \
       --gainref "$CPU64_GAIN" --dose_weighting --dose_per_frame 1.277 \
       --save_noDW --even_odd_split
CPU64_RUN_STATUS=$?
flock -u 9
# Retain CPU64_RUN_STATUS and require zero before using this run.
```

This template assumes the tutorial acquisition settings. A representative
experimental dataset must use its own validated optics/dose/gain metadata.
Retain immutable STAR, movie and gain SHA256 values, source/tree and binary
hashes, build flags and linked libraries. Pin one main build and one #178 build;
compare process layouts within each build before comparing treatments. Do not
combine #178 with the new fused-sum change and call that an isolated #178 result.

The production coordinator suppresses worker joint PDFs, stages checked movie
products, and publishes one complete canonical dataset STAR/report. Require its
ownership/exit, coverage, immutability and final `dataset_ready` checks to pass.
Production merging retains `_workers/wK/` provenance; its worker count, commands
and per-shard joint STAR inventory necessarily differ between layouts. Keep and
validate that provenance separately. For cross-layout identity, construct a
canonical published-product view containing every final file except this
`_workers/` namespace, then use the existing strict profiling identity helper:
complete MRC headers/payloads apart from the established writer-clock mask,
STAR/EPS content after output-root normalization, full canonical inventory, and
only the existing log/PDF-byte exclusions. Do not filter individual unexpected
movie products or metadata differences. Native ownership/coverage/publication
checks remain required. Retain failures and their original exits.

## Measurements and claims

Warm each arm once, then run at least six interleaved forward/reverse complete
blocks under the same confirmed allocation. Preserve all skips and incomplete
pairs. Report dataset-ready wall, worker-phase wall, throughput, CPU seconds,
faults, simultaneous sampled aggregate tree RSS and its sampling interval.
Summed individual process peaks are a different statistic; tree RSS may count
shared pages more than once. Include partition/setup, staging and final report
drain in the dataset endpoint, with identity verification outside timing.

Use the existing profiling paired statistics without changing gates. Report
paired differences, spread and unresolved outcomes; do not combine venues,
resource budgets, 12/24-frame inputs or historical revisions. Start with the
same frozen 24-movie input where available, then a representative heterogeneous
subset to expose stragglers. The prepared repeated-hardlink fixtures are useful
controls, not evidence about diversity across independent experimental movies.

**Current outcome:** native execution, dataset identity, throughput, RAM
capacity and NUMA effects are all pending. No speed or VM-memory conclusion is
established by the prepared tooling or the container-only budget refusals.
