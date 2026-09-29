# Old-source rejection for the composed suite — cpu64, 29 Sep 2026

Does the composed test suite still reject pre-composition production? A suite
that passes unchanged on main's source is not testing the composition.

Two arms, because the first answer was weaker than it looked.

## Arm 1 — composed tests, all of main's `src/`

`git checkout 6393547e -- src/` over the composed tree.

**Rejected at compile**, `build_rc=2`:

```
tests/test_patch_retry_state.cpp:52:33: error: 'bool MotioncorrRunner::alignPatch(...)'
    is private within this context
```

True, and a real rejection — but it only shows the test needs PR115's
access-specifier widening in `motioncorr_runner.h`. It does not show the suite
can see a behavioural regression, so it does not settle the question.

## Arm 2 — composed headers and tests, main's runner body only

`git checkout 6393547e -- src/motioncorr_runner.cpp`, keeping the composed
`motioncorr_runner.h` so it builds. 384 changed lines swapped back.

`build_rc=0`, then **22/23 with `MultiGpuScheduling` FAILED**, on the exact case
that should fail:

```
FAIL case_device_list_rejected: --gpu 0:1:2:3: in: src/motioncorr_runner.cpp, line 279
ERROR: --gpu was specified with --use_own, but MotionCorr was built without CUDA support (-DCUDA=ON).
```

That is precisely PR117's change. On main, a CPU-only build meets the
`_CUDA_ENABLED` guard first and reports only the missing CUDA support; PR117
moved list validation ahead of it so an unsupported device list is rejected for
the reason it is unsupported, in every build. The composed test sees the
difference and fails against the old body.

## What this does and does not establish

**`PatchRetryState` passes against main's runner body.** It is a
characterization test of a shift-accumulation contract PR115 exposed for
testing, not a regression detector for a composed change. Recording it as an
old-source rejection would be wrong.

So the device-free suite behaviourally rejects **one** composed production
change: PR117's `--gpu` validation. PR115's and PR118's production changes are
CUDA-side and a `-DCUDA=OFF` build cannot execute them at all — "23/23 CPU tests
pass" says nothing about those. Their coverage is the native suite (29/30 tests
on a real A100, all passing) and each owner's own old-source controls on their
own source, which are retained in their branches and are not re-derived here.
