# PR #252: native retry admission at 868d1fbb

**PASS:** isolated CUDA+nvCOMP Release compilation, the two focused host controls,
native admission boundaries, a discriminating native budget-omission mutant, and
one frozen e10216 reference with three constrained product-identity checks.
This closes the bounded native follow-up gap for **868d1fbb2394119a88dc5b02fdff77618109320b**.
It does not relabel the older bb348554 campaign or qualify D3/#251.

Read before work: issue [#226](https://github.com/KingAlejandro/MotionCorr-standalone/issues/226),
PR [#252](https://github.com/KingAlejandro/MotionCorr-standalone/pull/252), its
[retry-lifetime review](https://github.com/KingAlejandro/MotionCorr-standalone/pull/252#discussion_r4315391298),
[design/accounting note](../retry-admission-review.md), historical README/native.json,
and the retained QM patch/harness. The live PR head was the assigned source pin.
All committed changes are confined to this new evidence directory; production
sources, numerical gates, tolerances, dependencies and old evidence are unchanged.

## Source, build and resources

Fresh local branch `evidence/252-native-retry-20261022` starts at the assigned pin.
The initial T3 checkout was clean at `1f0a58bf6e0639d8b62f74da52f250cc664c0b30`;
no existing branch was moved. The separate root checkout was not modified.
Remote connection: `ssh -J ccp4-gateway 4GPUs`, verified hostname `4-gpu-vm`.
New scratch, retained in place:

```
/mnt/clathrin/alex-pr252-native-retry-20261022T150600Z
```

`git archive` at the source pin produced SHA-256
`011a21894775a9ace65da2abc235b8948cafaf5ce211ea93beb572bad2731db1`.
After restoring the mutant, **266/266** tracked `src/` and `CMakeLists.txt` files
match the pin; the complete expected hashes and observed `sha256sum -c` receipts
are retained. The sole source overlay for the positive native target is
[`native-receipts.patch`](support/native-receipts.patch): extra stdout receipts,
an 818-square/59-group case, and the literal 175,000,000-byte assertion in
`tests/cuda_local_admission.cpp`. No production overlay is present in the runner.

Resources: only GPU3, A100 80GB PCIe UUID
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`; CPUs **10-13**, inherited by children;
compile `--parallel 2`, runtime `--j 1`, numeric-library thread caps **1**.
The common build lock and canonical GPU3 correctness lock use nonblocking flock.
GPU3 is held across native tests and post-health, and reacquired across all four
runner cases through final health. Bench-lock probes occur before admission and
again after idle/health checks, and before each runner case. No foreign processes
are signalled. Compile and runtime receipts are separate; no performance comparison
or speed claim is made.

Toolchain: GCC 13.3.0, CUDA **12.8.61**, architecture 80, existing nvCOMP
**5.3.0.16** under `/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive`,
FFTW 3.3.10. Remote Python is `/home/alex/.mc-venv/bin/python3` (3.12.3,
NumPy **2.5.3**). Local receipt validation uses explicitly
`/Users/alex.konstantinov/.local/bin/python3`.
The configure warning about absent pbzip2 concerns the unrun InputFormats and
RealCutdown compressed-MRC cases; those suites are not credited and no required
check or tolerance was waived for this work.

The detached build ran 15:06:44–15:08:49 UTC, native controls
15:09:46–15:10:14 UTC, and the bounded runner 15:11:31–15:12:53 UTC on 2026-10-22.
Each has PID/start/finish/exit receipts; every phase exit is **0**.
[`build.sh`](support/build.sh), [`native.py`](support/native.py) and
[`products.py`](support/products.py) retain the exact configure/build/test/runner
argv and environment. Launch form, with `W` denoting this scratch:

```sh
nohup env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PATH=/usr/local/cuda-12.8/bin:/usr/local/bin:/usr/bin:/bin \
  taskset -c 10-13 /home/alex/.mc-venv/bin/python3 -I support/native.py \
  > logs/native-launch.log 2>&1 < /dev/null &
```

The build uses `taskset -c 10-13 bash support/build.sh`; products use the same
thread caps and affinity plus `CUDA_VISIBLE_DEVICES` set to the assigned UUID.
Scripts record the actual pinned paths and are single-campaign receipts, not an
instruction to overwrite this scratch for a reproduction.

## Native and host controls

`PatchRetryAdmission` and `PatchRetryState`: **2/2 PASS**, exit 0.
`CudaLocalAdmission` with the receipt overlay: **PASS**, CTest exit 0, followed by
a restored-helper direct rerun with exit 0. Real cuFFT plans and work queries are
used; only free bytes are wrapped. The local-stage boundary is **6,135,264 bytes**.
Four retry geometries each exercise S-1/S/S+1, incomplete-budget midpoint,
and complete-required-1/required/required+1: **28/28** expected decisions.
Invalid/overflow controls and the final pending-CUDA-error check also pass.

For the real e10216 geometry, S is **158,299,360 bytes**, fresh non-cuFFT alignment
buffers are **22,407,056 bytes**, and real C2R work is **11,112,768 bytes**.
The observed complete requirement is therefore **191,819,184 bytes**.
The literal **175,000,000** interval declines. Exact requirement admits;
required-minus-one declines.

The isolated [`omit-retry-budget.patch`](support/omit-retry-budget.patch) changes
exactly the helper's final assignment to publish S alone. Rebuilding the native
target against that helper is successful, then the test exits **1** with
`FAIL: incorrect complete retry admission boundary` at S for the first geometry.
This is the expected negative-control rejection, not a crash or numerical gate
change. The exact original helper bytes are restored, runner/native targets are
rebuilt, production-source hashes are checked and the positive native test passes.
Original, mutant and restored executable/helper hashes are all retained; executables
are not staged and no binary reproducibility claim is made.

## Actual runner fallback and products

The frozen input is the first e10216 movie, 4096×4096×59 signed-int16 MRC,
**1,979,712,512 bytes**, SHA-256
`f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56`.
Its digest matches the pinned corpus inventory before launch and is rechecked
afterward. Existing movie data is read through new scratch symlinks.
Available host RAM immediately before this campaign was **440,685,699,072 bytes**;
free scratch was **533,822,291,968 bytes**. Actual allocation/RSS is provenance.

The original QM harness is adapted only for new scratch/build paths, GPU UUID,
CPU allocation and `--j 1`; see [`qm-resources.patch`](support/qm-resources.patch).
The wrapper adds fail-closed resource checks and identity-checked balloon cleanup.
Original and adapted harness/comparator/balloon hashes are recorded. The existing
balloon executable is copied, never rebuilt or changed; its SHA-256 is
`3ede9c4fec56c3fbbae9a31b1bd75ed4abf01fab353f7b92e701fdb1f9747686`.
Its source is `486bfe4e361c3c2e7c1dd2298153a2d10721f3224aa5768ef95e72d477c13cd8`.

All four cases use `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150
--seed 1 --expected_frames 59 --i movies.star --j 1 --gpu 0 --ingest auto
--patch_x 5 --patch_y 5`, with case-specific output and witness paths.
The actual runner SHA-256 is
`8d787f0199c46b42212363a9ce335af3c9bae167d4c89efccddc2f740fbcce45`.

- **Unconstrained:** 81,154 MiB measured free; compact ingest, resident pipeline,
  batch chunk 4; runner exit **0**, all products and joint STAR published.
  Peak host RSS **2,042 MiB**.
- **8 GiB:** 8,189 MiB measured free; compact ingest, expected fused gain/sum
  allocation OOM, CPU preprocessing fallback and streaming alignment; exit **0**,
  strict MRC/STAR product comparison **PASS**, peak RSS **7,880 MiB**.
- **8.5 GiB:** 8,701 MiB measured free; compact ingest, resident preprocessing,
  batch chunk 0; retry admission declines at **78,839,808** available against
  **191,819,184** required, then streaming retry completes; exit **0**,
  strict MRC/STAR product comparison **PASS**, peak RSS **8,000 MiB**.
- **8.75 GiB:** 8,957 MiB measured free; compact ingest, resident pipeline,
  batch chunk 0; exit **0**, strict MRC/STAR product comparison **PASS**,
  peak RSS **2,042 MiB**.

The unmodified comparator validates one 4096×4096 image (16,777,216 pixels),
its per-movie STAR and joint STAR for every arm, and compares MRC header,
extended header and payload bytes plus STAR content. Its existing creation-time
label and output-prefix normalization are unchanged. **3/3 product checks exit 0**.
The separate whole non-PDF tree checks honestly retain **FAIL/exit 1** for each
constrained point: the only differing file is the per-movie `.log`, recording
intentional route/memory differences. No such FAIL is relabelled as whole-tree PASS.
Normal publication inventories and logs are retained. The harness removes only
its own constrained MRC/PDF bulk products after comparison; the reference and
all receipts remain remotely. No large 10441/Falcon4 campaign or full suite ran.

## Health, release and retained evidence

**198** nvidia-smi health samples check the assigned UUID, ECC counters,
row remapping and foreign compute processes. Every sampled ECC counter is zero;
remapped rows are zero with no pending/remap failure. Post-utilization settling
was predefined as at most twenty one-second samples, with all health checks at
every sample; no health exception was waived. Balloon cleanup checks saved PID
start time, command line and process group before signalling its own child;
all three balloons are reaped with expected SIGTERM exit -15.
At final collection (15:14:36 UTC), GPU3 has **1 MiB used, 0% utilization, no compute
processes**, and nonblocking GPU3/build/bench lock probes all exit **0**.
Kernel Xid logs are unavailable (`dmesg: read kernel buffer failed: Operation not
permitted`); the retained health evidence is CUDA checks plus nvidia-smi, not a
kernel-log audit.

- [`native.json`](native.json): statuses, resources, input/harness/binary hashes,
  exact case argv, routes, publication, comparator and cleanup receipts.
- [`raw-logs.tgz`](raw-logs.tgz): **156** indexed raw files, including build logs,
  CMake cache/flags/link argv, native positive/negative logs, phase exits/PIDs,
  STARs, per-movie logs, comparator reports, health and ownership records.
- [`raw-index.json`](raw-index.json) and [`archive.sha256`](archive.sha256): per-file
  size/SHA-256 and archive digest. Source archive, executables and bulk MRC/PDF
  products are excluded; exact source/binary/product identities are retained.
- [`retained-validation.json`](retained-validation.json): **PASS**, every archive
  entry/hash verified; 266 production identities, 28 native boundaries,
  the omission-mutant rejection, three strict product checks, three expected
  log-only whole-tree failures and all 198 health samples checked locally.

Read-only receipt verification:

```sh
/Users/alex.konstantinov/.local/bin/python3 \
  docs/rc0/issue226/d2/native_retry_20261022/support/verify.py
```

Preparation failures are recorded separately in [`preparation.json`](preparation.json):
the unconfigured hostname failed at the gateway's DNS layer; the configured alias
worked. One premature source-extraction attempt saw an in-flight transfer and
reported truncated gzip. No build/native job used that incomplete tree. The
completed archive was digest-verified and re-extracted before the sole build
launch. There were no unplanned native/runner retries or duplicate launches.

**UNRUN:** full CPU/CUDA/nvCOMP suites, 10441/Falcon4, scientific S1/QF,
performance qualification, physical smaller cards, host OOM and poisoned-device
experiments. This evidence supports the bounded D2 claim at the assigned source;
it does not recommend a merge. No push, merge, GitHub comment or Notion write was
performed; publication remains with the parent.

The published omission/resource patches use zero-context encoding to avoid
whitespace-only unified-diff context lines. Their application was checked to
produce exactly the same bytes as the executed patches retained in the raw archive.
