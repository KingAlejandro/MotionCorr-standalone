# Issue #69 — GPU work, prepared and waiting for an assigned slot

Nothing in this file has been run. #26 owns this round's initial GPU benchmark slot;
this task publishes its request and waits for Codex monitoring to assign one.

Branch `round96/69-claude-opus-5`. All of this is **correctness** work: it produces no
timing number, so it needs no quiescence gate. It does need the bench lock, because a
CUDA build and a 24-movie run both perturb whoever is measuring.

## Request

| Item | Value |
|---|---|
| Resource | one A100 on `4GPUs`, or a dedicated SCARF Slurm allocation |
| CPU | `taskset -c 96-103` on the top-level shell, build `-j8`, `OMP_NUM_THREADS<=8` |
| Mutex | `flock -w 2400 /tmp/motioncorr-bench.lock` around the whole series |
| Estimated wall time | ~10 min build, ~5 min fault matrix, ~15 min 24-movie control |
| Device state | read-only classification of the pending error. No `cudaDeviceReset`, no global cache drop, no other process or device touched |

## Commands

### 1. Build (queued behind the bench lock; may already be done)

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

### 5. Healthy same-backend 24-movie control

Base versus candidate, `-DCUDA=ON`, default options, all 24 tutorial movies. Compare
ordered pixels, literal MRC payloads, normalised full headers and the STAR artifacts,
with the four PDF differences and the MRC label timestamp preserved as known
non-reproducible items. Reuse the comparison logic in
`docs/issue69/harness/compare_cpu_arms.py`, which already carries its own negative
control.

## What will not be claimed

- No pass for any layer that has not run.
- The fault matrix cannot synthesise a genuinely poisoned context (an illegal address
  or an ECC fault), so the poisoned-context branch is not exercised by a real fault.
  That gap stays stated.
- Same-backend equality is not scientific equivalence and not a CPU/RELION Gate-2 pass.
- Clean nonzero failure is the supported contract where safe recovery is unavailable;
  it is not a successful CPU fallback.
