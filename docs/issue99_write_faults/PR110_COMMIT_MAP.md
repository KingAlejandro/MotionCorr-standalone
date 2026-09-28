# Integration mapping for PR #110 — PR #105 `RLIMIT_FSIZE` follow-up

For the owner of [`integrate/round96-correctness-foundation`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/110).
PR #110 already carries PR #105 at `910fcf431c038b3930cfd6919cebaeb02fc2295d`. This note
says what changed on PR #105 afterwards and how to take it.

**PR #110's tree was not modified by this work.** The verification below was done on a
throwaway local branch off `refs/pull/110/head`, with `--no-commit`, discarded afterwards,
and nothing was pushed.

## What to take

One commit. Tests only.

| commit | subject | files |
|---|---|---|
| `10842690b48aacdcd1c6404ba021ad8ce7676e5d` | `test(#99): preserve the inherited RLIMIT_FSIZE hard limit` | `tests/test_image_write_faults.cpp`, `tests/test_write_faults.py` |

Optional, documentation only, not required for a build or a test run:

| commit | subject | files |
|---|---|---|
| `318a324` | `docs(#99): evidence for the inherited-hard-limit delta, including a void control` | `docs/issue99_write_faults/**` |

**No production source changed.** `src/rwMRC.h`, `src/image.h` and
`src/micrograph_model.cpp` are byte-identical to what PR #110 already integrated at
`910fcf43`. `CMakeLists.txt` is unchanged, so PR #110's union resolution of that file is
untouched and does not need revisiting.

## It applies cleanly, verified

PR #110 carries both files at exactly their pre-delta blobs, so the cherry-pick is a
fast-forward of content with no conflict:

```
tests/test_image_write_faults.cpp  PR110 = f110c995…  = PR105@910fcf43   ->  e26b8942…
tests/test_write_faults.py         PR110 = cf8b013e…  = PR105@910fcf43   ->  bb74ec6c…
```

`git cherry-pick --no-commit 1084269` onto `refs/pull/110/head` (at `fe8ca55`) returned 0
with no conflict, and the resulting blobs are **identical** to PR #105's head:

```
tests/test_image_write_faults.cpp  applied e26b8942…  target e26b8942…  IDENTICAL
tests/test_write_faults.py         applied bb74ec6c…  target bb74ec6c…  IDENTICAL
```

## Why it is needed in the integration branch specifically

The defect is invisible on a host whose hard `RLIMIT_FSIZE` is infinite, because setting
an already-infinite hard limit to infinity is a no-op — so PR #110's current green run does
not indicate the problem is absent. It bites wherever a finite hard limit is inherited,
which is common on CI runners and HPC schedulers. There it fails *before* the writer fault
is injected:

- `WriteFaults` → `subprocess.SubprocessError: Exception occurred in preexec_fn.`
- `ImageWriteFaults` → `what(): setrlimit(RLIMIT_FSIZE) failed`, `Subprocess aborted`

Both look like the fault never firing, i.e. like a regression in the writer fix that PR
#105 exists to deliver.

## Re-running the discriminating control after integration

```sh
cd <build dir>
bash -c 'ulimit -f 8192; ctest -V -R "ImageWriteFaults|WriteFaults"'
```

Use `ulimit -f N`, **not** `ulimit -H -f N`. The latter sets only the hard limit and leaves
the soft limit at infinity, so `soft > hard`, `setrlimit` returns `EINVAL`, and no limit is
applied at all — the tests then pass without the condition ever being in force. Confirm
with `python3 -c "import resource;print(resource.getrlimit(resource.RLIMIT_FSIZE))"`, which
must print `(8388608, 8388608)` and not `(-1, -1)`.

The tests also carry their own unprivileged finite-hard-limit control, so a plain `ctest`
run exercises it too; the shell-level version above is the independent check.

Evidence: `docs/issue99_write_faults/REPORT.md` addendum, with
`cpu-finite-hard-limit-control.log` and `cpu-rlimit-validation.log`.
