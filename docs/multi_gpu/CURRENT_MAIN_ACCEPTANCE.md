# Current-main static workers and complete dataset endpoint

This candidate starts at `57e98666` (130/131/132/137 included) and ports the
reviewed process-per-device tools from post 128 `7bc2168b`. Original commits and
cherry-pick provenance are retained. No CUDA kernel, pool 136/140, old 122 driver,
reader-pool 121 or experimental 93 code is imported.

`run_multi_gpu.py` ends at **workers_complete**. `run_dataset.py` additionally
stages all requested movie products and calls one `--aggregate_only` owner.
**dataset_ready** requires canonical joint STAR, full requested report,
unmodified movie contents/mtimes, and successful owned-process completion.
Private report staging is published with the joint STAR last. Normal resume and
`--do_at_most` retain their original behavior; aggregate-only rejects partial
processing. Report pages follow original input order, which can differ from the
older directory-glob report order. Scientific products are unchanged.

`--aggregate_only` preflights option/frame completeness and requested movie EPS.
The merger independently verifies before/after movie contents/mtimes and final
joint rows. It requires a fresh output directory. These checks do not provide a
filesystem transaction against unrelated concurrent mutation of movie files.

## Current host controls and remaining gates

- Required test collection: **33**, preserving current `NativeMovieStaging` and
  adding `MultiGpuScheduling`. Collection is not an execution verdict.
- Scheduler: 55 CPU/device-free/actual-CLI controls. Aggregate controls use an
  **explicit fake Ghostscript** on hosts without the renderer; they prove
  command/failure/publication behavior, not real PDF rendering.
- Owned tree-RSS and coordinator controls run normally and with `python -O`.
  RSS is the instantaneous sum of owned processes, not the sum of VmHWM.
  Shared pages are double-counted; short peaks/children can escape polling.
  PSS is optional. No `/proc`, missing readings or sampler failure remain
  `UNAVAILABLE`/`INCOMPLETE`/`NO_SAMPLES`, never invented zero measurements.
- Mac full-suite `SyntheticRegression` fails its historical Linux output
  reference; the exact unchanged-main control reproduces the same metrics.
  `NativeMovieStaging` skips on this platform. No gate is relaxed.
- **UNRUN:** full Linux 33 execution, CUDA compile/native 41/42 collection and
  execution, real Ghostscript report rendering/content, current-source native
  serial/2/4 products/failure/resume, Linux live process-tree memory and timing.
  Collect the actual configuration's native inventory; do not infer a PASS
  from a predicted count or previous-source evidence.

## Executable native correctness plan (after review and allocation)

Use one frozen Release binary and input/source/tool hashes. Work from the data
project directory so original relative movie names retain their meaning. Obtain
four exclusively granted physical UUIDs and 24 actual allowed logical CPUs;
record job/PID/start/executable, physical-core/SMT/NUMA topology and memory policy.
Do not hardcode CPU 0–23 or disturb existing campaigns. Set these from the actual
allocation, with two 12-wide and four 6-wide disjoint partitions of the same 24 CPU
union:

```sh
python3 tests/test_aggregate_only.py --binary "$TASK_BINARY"
python3 tools/validate_test_collection.py --test-dir "$TASK_BUILD"
ctest --test-dir "$TASK_BUILD" --output-on-failure

python3 tools/multi_gpu/run_dataset.py \
  --binary "$TASK_BINARY" --star "$TASK_STAR" --out "$TASK_OUT/w1" \
  --launcher-args="--devices $TASK_UUID1 --cpus $TASK_CPU24 --cpu-budget24" \
  --required-products='.mrc,.star,_shifts.eps' -- \
  --use_own --j24 --max_io_threads24 --ingest auto \
  --angpix "$TASK_ANGPIX" --voltage "$TASK_VOLTAGE" \
  --dose_weighting --dose_per_frame "$TASK_DOSE" --gainref "$TASK_GAIN"

python3 tools/multi_gpu/run_dataset.py \
  --binary "$TASK_BINARY" --star "$TASK_STAR" --out "$TASK_OUT/w2" \
  --launcher-args="--devices $TASK_UUID1,$TASK_UUID2 --cpus $TASK_CPU12_A;$TASK_CPU12_B --cpu-budget24" \
  --required-products='.mrc,.star,_shifts.eps' -- \
  --use_own --j12 --max_io_threads12 --ingest auto \
  --angpix "$TASK_ANGPIX" --voltage "$TASK_VOLTAGE" \
  --dose_weighting --dose_per_frame "$TASK_DOSE" --gainref "$TASK_GAIN"

python3 tools/multi_gpu/run_dataset.py \
  --binary "$TASK_BINARY" --star "$TASK_STAR" --out "$TASK_OUT/w4" \
  --launcher-args="--devices $TASK_UUID1,$TASK_UUID2,$TASK_UUID3,$TASK_UUID4 --cpus $TASK_CPU6_A;$TASK_CPU6_B;$TASK_CPU6_C;$TASK_CPU6_D --cpu-budget24" \
  --required-products='.mrc,.star,_shifts.eps' -- \
  --use_own --j6 --max_io_threads6 --ingest auto \
  --angpix "$TASK_ANGPIX" --voltage "$TASK_VOLTAGE" \
  --dose_weighting --dose_per_frame "$TASK_DOSE" --gainref "$TASK_GAIN"
```

Keep every helper/aggregate inside the 24 CPU union (the coordinator applies it
where Linux affinity is supported). The three commands cap aggregate decoder
concurrency at 24; record actual paths/achieved concurrency. The output option
values above must match the frozen fixture contract; use its exact patch,
selection/grouping/binning settings too. This is a correctness plan, not an
executed benchmark or a new CPU recommendation.

First all 24 tutorial movies. Grade complete finite pixels, full normalized 1024
bytes and extended MRC headers, all per-movie STAR/model/optics/exposure/frame
fields and canonical joint order. Compare report page coverage/data/rendered
content, declaring only path/date metadata allowances. Add smaller separate
DW+noDW, PS and EVN/ODD product arms with the corresponding required suffixes.
Missing physical UUID/ingest witnesses, products or reports must fail the row.

Inject one owned worker/TERM-ignoring descendant failure, a late writer fault
and report failure. Require named failure, no dataset-ready success, retained
healthy movies and all owned children gone before release. For non-prefix
resume, make a middle shard product incomplete; repair only that work with
ordinary resume in its existing worker directory, retaining healthy hashes and
mtimes, then stage/aggregate afresh and compare with baseline. The dataset
coordinator deliberately refuses an existing run directory rather than
silently replacing provenance.

Only after native completeness, use at least five balanced/interleaved 1/2/4
blocks with the same allocation, CPU/IO budget, options/cache/storage and full
output set. Record total dataset-ready wall plus worker/aggregate stages and
simultaneous summed-RSS/PSS/UUID-filtered VRAM traces. Every timed tree must be
graded; missing baseline excludes dependent rows. Real distinct EMPIAR10361
inputs and 100–240 repeated tutorial movies answer different questions; label
repeated-input throughput honestly. Gain/no-gain and storage/wait-policy arms
remain separate. Do not combine historical venues, multiply single-GPU gains
or interpret a worker-only timer as completed dataset throughput.
