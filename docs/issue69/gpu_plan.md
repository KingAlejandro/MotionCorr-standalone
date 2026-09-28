# Issue #69 — GPU work, prepared and waiting for an assigned slot

Nothing in this file has been run, except the build in step 1, which was compile-only
and executed nothing on a device. #26 owns this round's initial GPU benchmark slot;
this task publishes its request and waits for Codex monitoring to assign one.

Branch `round96/69-claude-opus-5`. All of this is **correctness** work: it produces no
timing number, so it needs no quiescence gate. It does need the bench lock, because a
CUDA build and a 24-movie run both perturb whoever is measuring.

## Request

| Item | Value |
|---|---|
| Resource | one A100 on `4GPUs`, or a dedicated SCARF Slurm allocation. Revised round envelope: at most **2** of the four GPUs are available initially |
| CPU | aggregate round budget is cores **96-111** (16 logical CPUs, all NUMA node 1), build **<= 8**. This task uses `taskset -c 96-103` on the top-level shell, a subset of it, with `OMP_NUM_THREADS<=8` |
| Mutex | `flock -w 2400 /tmp/motioncorr-bench.lock` around the whole series |
| Estimated wall time | ~10 min build, ~5 min fault matrix, ~15 min 24-movie control |
| Device state | read-only classification of the pending error. No `cudaDeviceReset`, no global cache drop, no other process or device touched |
| Must be recorded per run | chosen cores, inherited cpuset, CPU/NUMA/memory policy, and the actual GPU UUID from `nvidia-smi --query-gpu=index,uuid,name --format=csv` — not the advertised device index |

## Commands

### 0. Record the resource context before anything else

```
taskset -cp $$
cat /proc/self/cpuset
numactl --show 2>/dev/null
nvidia-smi --query-gpu=index,uuid,name,memory.used --format=csv
```

A device index is not an identity: record the UUID of the GPU actually used.

### 1. Build (done for the current head; see evidence/cuda-compile.log)

```
export PATH=/usr/local/cuda/bin:$PATH
cmake -S <src> -B <build> -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON
cmake --build <build> -j8
```

### 2. Fault matrix — `tests/cuda_fault_matrix.cpp`

```
<build>/cuda_fault_matrix
```

Sweeps every ordinal of every wrapped primitive a clean run uses, so the sites the
issue enumerates are covered by construction: session real / Fourier / sum / gain
allocation, cuFFT create / plan / work-area attachment, patch scratch allocation, H2D
and D2H, launch completion (via the synchronisation the production code already does
after its launches), and reconstruction. Per trial it records the stage reached, the
exit mechanism, released owned allocations, preserved borrowed inputs, and the survival
of an earlier completed product. A successive-movie pass with the fault on the third
movie exposes cross-movie leaks and stale cache state.

It checks its clean baseline first and refuses to report anything if that is not clean,
so it cannot pass by failing to observe.

Expected records, to be filled in from the actual run, not in advance:

| Primitive | Ordinal | Stage reached | Exit | Owned released | Borrowed intact | Earlier product |
|---|---|---|---|---|---|---|

### 3. Existing control, unchanged

```
<build>/cuda_wrapper_upload_failure
```

Six injected owned-allocation upload failures. Already passing on main; re-run to show
this branch did not regress it.

### 4. Forced-nonconvergence end-to-end witness for the retry fix

The CPU control `tests/test_patch_retry_state.cpp` establishes that `alignPatch`
accumulates, which is the premise of the fix, but the production retry is inside
`#ifdef _CUDA_ENABLED` and cannot run in a CPU-only build. The end-to-end witness is:

1. Build base `4c952b3f` and this branch, both `-DCUDA=ON -DCMAKE_BUILD_TYPE=Release`.
2. Run both on the tutorial movies with `--patch_x 5 --patch_y 5` and a temporarily
   lowered `max_iter` so some patches genuinely fail to converge on the device and take
   the retry. `max_iter` is already a command-line option, so this needs no source
   change and no fault switch.
3. Compare the per-patch local trajectories in the per-movie STAR files. On base the
   retried patches should carry roughly twice the shift the candidate reports; on the
   candidate they should match a single estimate.
4. Control: the same pair at the default `max_iter`, where no patch takes the retry,
   must produce identical output.

Step 4 is the load-bearing one. Step 3 changes behaviour on purpose, so an
identical-output assertion there would be the wrong test.

### 5. Early-binning streaming path — pass criterion 4's second half

Issue #69's pass criteria require that "the early-binning streaming path remains
supported where previously valid", and an earlier version of this plan did not mention
it. `CudaMovieSession` is only constructed when `use_gpu && !early_binning`
(`motioncorr_runner.cpp:1425`), so with `--early_binning` the resident path is never
entered: F3 and F4 live inside the session, F6 is behind `if (movie_session && ...)`,
and F7's buffer is only allocated inside the `if (movie_session)` block. F1 and F2 are
reached only through the non-resident `cudaAlignPatch` wrapper. F5's two `assign`
statements *do* execute -- they are inside `#ifdef _CUDA_ENABLED` but not behind a
`movie_session` test -- and are provably no-ops there, because the vectors are still
zero when no device attempt ran. An earlier version of this paragraph said none of the
F-lines are entered, which overstated it. The control is correspondingly
simple and must still be run:

```
<build>/motioncorr --i <movie> --o <out> --use_own --gpu 0 --bin_factor 2 --early_binning ...
```

base versus candidate, outputs compared byte for byte with
`docs/issue69/harness/compare_cpu_arms.py`. Expected: identical, because the candidate
adds no statement that path executes. If it is not identical, that is a finding.

### 6. Healthy same-backend 24-movie control

Base versus candidate, `-DCUDA=ON`, default options, all 24 tutorial movies. Compare
ordered pixels, literal MRC payloads, normalised full headers and the STAR artifacts,
with the four PDF differences and the MRC label timestamp preserved as known
non-reproducible items. Reuse the comparison logic in
`docs/issue69/harness/compare_cpu_arms.py`, which already carries its own negative
control.

### 7. Relocation-level check that the interposition actually took effect

`nm` showing `__wrap_*` defined in the binary proves only that the test translation
unit defines them. To show the linker actually redirected `motioncorr_core`'s calls:

```
objdump -d --demangle <build>/cuda_fault_matrix \
  | awk '/<cudaAlignPatchDevice.*>:/{f=1} f&&/call/{print} /^$/{f=0}' \
  | grep -E "cudaMalloc|cufft" | head
```

Every such call must target `__wrap_...`, not the bare symbol. This is a read-only
disassembly, needs no device, and can be done at build time.

## Pass criterion 3 is not this task's

"Retry reprocesses partial even/odd/DW products; prior complete artifacts are
preserved" is a completion/resume property. It belongs to #99/#53's publication
contract, and this branch neither implements nor claims it. Recorded so it is visibly
deferred rather than silently missing.

## What will not be claimed

- No pass for any layer that has not run.
- The fault matrix cannot synthesise a genuinely poisoned context (an illegal address
  or an ECC fault), so the poisoned-context branch is not exercised by a real fault.
  That gap stays stated.
- Same-backend equality is not scientific equivalence and not a CPU/RELION Gate-2 pass.
- Clean nonzero failure is the supported contract where safe recovery is unavailable;
  it is not a successful CPU fallback.
