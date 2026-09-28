# Issue #99 — executed evidence: fail-closed MRC image writes

Everything below was run. Where a layer was not run, it says so.

| Field | Value |
|---|---|
| Host | `small-refmac-machine` (cpu64), 64 cores, `taskset -c 32-63`, `flock /tmp/motioncorr-issue96-cpu-validation.lock` |
| Date | 2026-09-27T23:58Z (build/CTest), 2026-09-28T00:01Z (evidence) |
| Toolchain | cmake 4.4.3, g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, Python 3.12.3 |
| Build | `-DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON`, `CMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG`, `--parallel 16` |
| Candidate | `f83a4669e3b37108def1e8ce147b2291c44c4a6a` (fix + tests, after independent review) |
| Negative control | `dddc6763b03e33a114dbbf9ea21e31de1549129c` = pre-fix main `4c952b3f` **plus the new tests only** |
| GPU | **not run.** Every fault is injected at the host stdio layer and is backend-independent; no CUDA arithmetic, gate or output default is touched. |

Raw logs: [`cpu-validation.log`](cpu-validation.log), [`cpu-evidence.log`](cpu-evidence.log).
Scripts as executed: [`cpu_validation.sh`](cpu_validation.sh), [`cpu_evidence.sh`](cpu_evidence.sh).

## Binary and input provenance

```
candidate  motioncorr          59936bbec5d13105f54fe52a5c5d7221126923593a7edd3593c6aaf291e0a1d1
pre-fix    motioncorr          b9d16a2d8a69500c8ba8671382716a9cf79e851c2fa8264ed6735f2e3e5c82d8
input      synthetic_movie.tiff 95b5f0d37d481355b8abe30f7380c33d9ea173a87bec6e8fc3e567c057622bd4
```

Both trees were staged from a bundle and verified at `0 modified files`.

## 1. The reproducer the audit did not have

Issue #99 recorded that no disk-full, injected short-write, EIO, flush/close or end-to-end
false-success experiment had been executed. This is that experiment, run against
**unmodified pre-fix main**.

`RLIMIT_FSIZE = 599040` bytes, `SIGXFSZ` ignored, private temporary directory; the output is
1 024 + 512×512×4 = 1 049 600 bytes, so exactly the image write fails. No shared disk was
filled.

```
phase 1 (movie a alone, unlimited)   exit=0   a.mrc = 1049600 bytes
phase 2 (a+b, --only_do_unfinished, limit applied)   exit=0
  b.mrc on disk:                        599040 bytes   <- truncated
  b.star completion record present:     YES
  joint STAR after the failed write:
      out/mov/a.mrc out/mov/a.star  1  6.099077 4.164012 1.935065
      out/mov/b.mrc out/mov/b.star  1  6.099077 4.164012 1.935065
  " Written: out/corrected_micrographs.star"
  " Done! Written: out/logfile.pdf"
```

Pre-fix, a short image write produces a truncated micrograph, a completion record claiming
success, **exit 0**, and a joint STAR plus logfile.pdf publishing the truncation to
downstream processing. That is the false completion this issue is about, now executed
rather than inferred.

The unit-level control reproduces the second defect just as directly. On pre-fix main the
new `ImageWriteFaults` binary does not merely fail, it **aborts**:

```
FAIL: a short payload write must throw, not report success
FAIL: the failure must name the output path, got:
in: src/image.h, line 374
ERROR:
Can not close image file
terminate called after throwing an instance of 'RelionError'
```

`src/image.h:374` is `fclose` inside `~fImageHandler`. Throwing from an implicitly
`noexcept` destructor is `std::terminate`, so the only check that existed in the chain
could not report a failure — it could only kill the process, unnamed.

## 2. Post-fix behaviour, same injected fault, same binary arguments

```
phase 1 (a alone, unlimited)   exit=0   a.mrc = 1049600 bytes
phase 2 (a+b, --only_do_unfinished, limit applied)   exit=1   (exit status, not a signal)
  reported: Failed to write image data (1048576 bytes) to out/mov/b.mrc: File too large
            Motion correction failed for 1 movie(s): mov/b.tiff.
            Successful per-movie outputs were retained; joint output was not generated.
  b.star completion record present:     no
  a.mrc unchanged:                      yes
  joint STAR unchanged (b withheld):    yes
phase 3 (repaired retry, limit lifted)   exit=0
  b.mrc now 1049600 bytes, b.star present, a.mrc still unchanged
  joint STAR now lists a.mrc and b.mrc
```

Against the acceptance criteria, in order: the injected short write is detected; it cannot
produce a completed-movie state; the failure is nonzero and names the movie
(`mov/b.tiff`), the product (`out/mov/b.mrc`) and the stage (`image data`); no completion
marker is left; the joint output is withheld; the earlier healthy movie is preserved
byte-for-byte; and `--only_do_unfinished` retries the incomplete product and repairs it.

## 3. Both fault classes are detected at the layer that can see them

Verbose `ImageWriteFaults` on the fixed build:

```
in: src/rwMRC.h,  line 609  Failed to write image data (1048576 bytes) to …/big.mrc: File too large
in: src/image.h,  line 455  Failed to flush and close image file …/small.mrc: File too large
  destructor dropped 1464 unflushable bytes without terminating
image write faults: ok
```

Two different files and two different detection points, by construction:

- `big.mrc` is 512×512, so the 1 MiB payload is larger than any stdio buffer and goes out
  through a direct `write(2)`. The short count reaches the **`fwrite` check** in `rwMRC.h`.
- `small.mrc` is 16×16, so header plus payload is 2 KiB and is still entirely in the stdio
  buffer when the last `fwrite` returns full success. Nothing has reached the fd. Only the
  **checked close** in `image.h` can see it. This is the case the issue singled out, and it
  fails if write counts alone are checked.
- The third line is the regression guard for the abort shown in §1. It proves its own
  precondition rather than merely surviving: 3000 bytes were buffered under a 1536-byte
  limit and 1464 of them could not be flushed, so "did not terminate" is a statement about
  a stream that really did fail.

The test also runs a healthy control that round-trips the payload, and a negative control
that repeats each fault with the limit lifted, so a passing assertion cannot be some
unrelated error being mistaken for the injected one.

## 4. Healthy output is unchanged

Same input, same arguments, same relative paths, pre-fix versus post-fix binaries:

```
mov/p.mrc                   neg=beb91c2ff74aaa98…  head=beb91c2ff74aaa98…   1049600 bytes
mov/p.star                  neg=18add2f32fe1708b…  head=18add2f32fe1708b…
corrected_micrographs.star  neg=89d486d7ebaa72ed…  head=89d486d7ebaa72ed…
```

Whole-file SHA-256, header included, not just the payload. A separate run under differing
output paths gave the same payload hash
`1a424122f6fd8f9b691197f92d9a6ca712458e9f51898e34232ad3ad271ce9d3`, which is also the
payload hash the pre-review revision of this branch produced — the review follow-up
commits changed no output byte.

Two files in that comparison are **not** identical, and neither is a content difference:

- `mov/p.log` differs on exactly one line — `Full movie wall time: 0.036 s` versus
  `0.047 s`. Measured wall time.
- `logfile.pdf` differs in 83 bytes and 6 bytes of length, with identical
  `/CreationDate`. This is the pre-existing ghostscript PDF nondeterminism already recorded
  for this project; it is preserved and not claimed as parity.

## 5. Full CPU CTest suite, candidate build

15/15 passed, including the two new tests:

```
Runner_failure  Runner_invalid  RunnerExposure  HotPixelRngDeterminism  Runner_tomography
RunnerExportedUnits  SyntheticRegression  RunnerLateBin  DamagedMovie  RunnerModelParser
TiffRead  ImageWriteFaults  WriteFaults  Runner_resume  GainCache
```

On the negative-control build the same two new tests fail (`ctest` exit 8), one by
assertion and one by `SIGABRT`, as shown in §1. Nothing else in the suite was run against
the negative control.

The negative control must *build* to be a control. An earlier revision of
`tests/test_image_write_faults.cpp` used an API that exists only after the fix, so it did
not compile on the pre-fix tree and `ctest` recorded `ImageWriteFaults` as `Not Run` —
which the harness counted as a failure and which could have been read as the defect being
detected. The test was rewritten to use only the pre-fix `fImageHandler` interface, the
harness now aborts the run outright if the control fails to build, and the result above is
from a control that compiled and ran.

## 6. Coverage limit: the header write, measured not assumed

The issue's plan lists a failed/short **header** write as its own injection. The check for
it exists (`mrcWriteBlock(fimg, header, MRCSIZE, "MRC header")`), but on this host a fault
cannot be made to land on that `fwrite`'s return, and that was measured rather than
assumed. Probe log: [`header-stage-probe.log`](header-stage-probe.log).

```
st_blksize(/tmp)=4096  BUFSIZ=8192
limit 0, 512x512:  rwMRC.h:609  Failed to write image data (1048576 bytes) … File too large
limit 0, 16x16:    image.h:455  Failed to flush and close image file …     File too large
```

Even with `RLIMIT_FSIZE = 0` the 1024-byte header always fits the stream buffer, so it
never reaches `write(2)` inside its own `fwrite`; the identical fault surfaces at the next
flush point instead, and both of those points are asserted above. On a filesystem
reporting `st_blksize <= 1024` the header `fwrite` would flush in place and the
`MRC header` stage label would appear. This sub-case is therefore **covered in code and
unrun as a distinct observation**, and is recorded as unrun rather than claimed.

## 7. What is not claimed

- **Not claimed: crash durability.** No `fsync` was added. The claim is that an error
  *reported* by the C library or the kernel for any write, seek, flush or close this
  process performs is now propagated as a named per-movie failure. Bytes whose write
  returned success are not asserted to survive a machine crash, and a filesystem that
  reports a write-back error to nobody remains out of reach of any non-`fsync` fix.
- **Not claimed: publication atomicity.** A failed write still leaves a truncated file on
  disk. That is safe today only because `completeMrc` length-validates it on resume — which
  §2 phase 3 demonstrates — and because nothing consumes an output whose movie failed the
  batch. Temporary paths, ordered publication and completion identity are PR B.
- **Not run: GPU, and any CUDA-backend re-run of these two tests.** No timing measurement
  of any kind was taken; #85 owns write performance and #26 owns this round's benchmark
  slot.
- **Not covered by PR A:** cancellation during output, the full per-product failure matrix
  across DW/noDW/EVN/ODD/PS, and changed gain/options. These are listed against PR B in
  `agents/designs/issue_99_fail_closed_image_writes.md` §7.



---

# Addendum — inherited `RLIMIT_FSIZE` hard limit (Codex review on PR #105)

[`discussion_r4119251206`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/105#discussion_r4119251206),
raised at `910fcf43`. **Tests only — `git diff 910fcf4..57ba661 -- src/ CMakeLists.txt` is
empty.** Everything recorded above still holds; the ghostscript PDF nondeterminism (§4) and
the measured-unreachable MRC header-write injection (§6) are both preserved.

| Field | Value |
|---|---|
| Host | `small-refmac-machine` (cpu64), `flock /tmp/motioncorr-issue96-cpu-validation.lock` |
| Date | 2026-09-28T07:07Z → 07:09Z |
| Payload cpuset | `taskset -c 32-63`; witnessed inside the build as `Cpus_allowed_list: 32-63` |
| NUMA | 2 nodes; node 0 = cpus 0-31 (115 839 MB), node 1 = cpus 32-63. `Mems_allowed_list: 0-1` |
| Memory policy | `numactl --show` → `policy: default`, `preferred node: current`, `cpubind: 1` (the 32-63 half) |
| Load (shared host) | 6.75 at start, 9.81 at end — not idle; no timing was taken |
| Build | Release `-O3 -DNDEBUG`, CUDA=OFF, `--parallel 16` |
| Candidate | `57ba66180e1e9fe64a48551364985d49d2853a1b` |
| Harness control | `fb2fab8e6b91356e796d10f38a7891459b212428` — this branch's **fixed writer** with the **pre-delta tests** |
| Negative control | `2101c3c3a1c1fd1a41b2ac7ad62c48097c4eba41` — pre-fix main `4c952b3f` with the **new** tests |
| GPU / timing | none, neither run nor claimed |

Log: [`cpu-rlimit-validation.log`](cpu-rlimit-validation.log). Script as executed:
[`cpu_rlimit_validation.sh`](cpu_rlimit_validation.sh).

```
candidate       motioncorr           a8285e2c2b84d85d778ad5f758edcec88b602b64ce0636273c403b4a84d58baa
candidate       image_write_faults   5a8f008ab3964d97c181bf0819174be95a077dffdd56989015528f89ae25f861
harness control image_write_faults   036d5eeeac45648943a399bad2b030d024493fa0b97dcb2b56a9e9a90838f231
negative ctrl   motioncorr           489e5532cf4efa342f11d71f35ed6d991837d3ef47cba114da0fcfd4fca462f0
input           synthetic_movie.tiff 95b5f0d37d481355b8abe30f7380c33d9ea173a87bec6e8fc3e567c057622bd4
```

## A1. The defect

Both fault tests wrote `RLIM_INFINITY` as the **hard** limit. An unprivileged process
cannot raise a hard limit, so under the finite inherited hard `RLIMIT_FSIZE` that CI and
HPC systems set, the C++ suite raised `setrlimit(RLIMIT_FSIZE) failed` while *restoring*,
and the Python `preexec_fn` failed in the forked child so MotionCorr never `exec`'d. Either
way the harness dies before the writer fault is injected — which presents as "the fault did
not fire", the opposite of the truth.

## A2. The fix

Both paths read the inherited `(soft, hard)`, lower only the soft limit, clamp the
requested soft value to the hard one, and restore exactly what was inherited. Both also
refuse up front, naming the numbers, if the inherited hard limit is below the
1 049 600-byte healthy product — that is an environment the suite cannot host, not a writer
defect.

Fixing it quietly would not be provable: on a host with an infinite hard limit the *old*
code also passes, because writing infinity over infinity is a no-op. So both tests create
the condition themselves, unprivileged — the C++ suite forks and re-execs with
`hard = 8 MiB`; the Python test adds phase 4 driving MotionCorr through a `preexec_fn` that
lowers the child's hard limit.

## A3. The control discriminates, at two different hard limits

`ulimit -f N` sets **both** soft and hard. The harness refuses to proceed if the resulting
hard limit is still infinity, so the run cannot be void without saying so.

```
candidate, ulimit -f 8192   -> (8388608, 8388608)   exit=0   both tests Passed
    phase 4 precheck: child hard limit 8388608 B (inherited 8388608)
    phase 4: finite hard limit 8388608 B -> exit 1, MotionCorr reported the short
             write on c.mrc, c.mrc truncated to 600000 B, no c.star
    ImageWriteFaults: control child ran at soft=8388608 hard=8388608

candidate, ulimit -f 4096   -> (4194304, 4194304)   exit=0   both tests Passed
    phase 4 precheck: child hard limit 4194304 B (inherited 4194304)
    phase 4: finite hard limit 4194304 B -> exit 1, ... (reports what was applied)
    ImageWriteFaults: "inherited hard limit is already 4194304 bytes; outer run covered it"

pre-delta tests, ulimit -f 8192                      exit=8   both FAIL
    WriteFaults:       subprocess.SubprocessError: Exception occurred in preexec_fn.
                       (after phase 1 wrote a.mrc 1049600 B -- so it died in the
                        injection setup, not at a writer assertion)
    ImageWriteFaults:  what():  setrlimit(RLIMIT_FSIZE) failed   [Subprocess aborted]

pre-delta tests, no finite hard limit                exit=0   100% passed
```

The last line isolates the cause: the pre-delta tests fail **only** when the hard limit is
finite. The 4 MiB row is the case both reviewers flagged — an inherited hard limit that is
already finite but below the 8 MiB the control wants must not become a spurious failure.

Phase 4 asserts on MotionCorr's own `Failed to write image data (N bytes) to <path>`
message, matched as a **single** message containing the product name, not two independent
substrings and not an exit code — a failed spawn is also nonzero, and `c.mrc` alone also
appears in ordinary progress output.

## A4. Vacuity guard

The C++ control's `(finite hard limit)` label used to come only from the
`MC_WRITE_FAULTS_IN_CHILD` marker, so a stray value in the environment would have skipped
the control and still printed it. It now cross-checks the actual limit:

```
$ MC_WRITE_FAULTS_IN_CHILD=1 ./image_write_faults          exit=1
  inherited RLIMIT_FSIZE: soft=infinity hard=infinity  (finite-hard-limit control child)
FAIL: MC_WRITE_FAULTS_IN_CHILD is set but the hard RLIMIT_FSIZE is infinity, not the
      <= 8388608 this control imposes. Refusing to report a control that did not run.
```

A missing `argv[0]` is likewise a failure rather than a silent skip.

## A5. The first attempt at the external control was void, and is kept in the record

`bash -c 'ulimit -H -f 8192; …'` **fails**: bash sets only the hard limit and leaves the
soft limit at infinity, so `soft > hard` and `setrlimit` returns `EINVAL`.

```
bash: line 1: ulimit: file size: cannot modify limit: Invalid argument
  rc=1
  resulting pair: (-1, -1)          <- RLIM_INFINITY; no limit was ever applied
```

Under that first attempt both the candidate *and* the pre-delta tests passed, which reads
exactly like "the delta was unnecessary". The harness now aborts rather than run void, and
this is recorded because a control that silently fails to apply its own condition is the
same failure mode this issue's tests exist to catch.

## A6. Everything else, re-run at the candidate

- Full CPU CTest, normal environment: **15/15 passed**.
- Negative control — pre-fix main with the **new** tests: **exit 8, both fail, for the
  writer reason**: `AssertionError: a failed image write was treated as success`,
  `FAIL: a short payload write must throw, not report success`,
  `terminate called after throwing an instance of 'RelionError'`. The delta did not blunt
  the control.
- Healthy payload: `1a424122f6fd8f9b691197f92d9a6ca712458e9f51898e34232ad3ad271ce9d3`,
  1 049 600 bytes — unchanged from every earlier revision on this branch.
