# Issue #99 — executed evidence: fail-closed MRC image writes

Everything below was run. Where a layer was not run, it says so.

| Field | Value |
|---|---|
| Host | `small-refmac-machine` (cpu64), 64 cores, `taskset -c 32-63`, `flock /tmp/motioncorr-issue96-cpu-validation.lock` |
| Date | 2026-09-27T23:58Z (build/CTest), 2026-09-28T00:01Z (evidence) |
| Toolchain | cmake 4.4.3, g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, Python 3.12.3 |
| Build | `-DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON`, `CMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG`, `--parallel 16` |
| Candidate | `239320f61c43576ebff97e378ab1cc0835ce8eae` (fix + tests), tree `19a5b36bb973f1df84b818c760b0d69c640a35ec` |
| Negative control | `39220eac57ecb4b0228d5e3f9152d7984363b045` = pre-fix main `4c952b3f` **plus the new tests only** |
| GPU | **not run.** Every fault is injected at the host stdio layer and is backend-independent; no CUDA arithmetic, gate or output default is touched. |

Raw logs: [`cpu-validation.log`](cpu-validation.log), [`cpu-evidence.log`](cpu-evidence.log).
Scripts as executed: [`cpu_validation.sh`](cpu_validation.sh), [`cpu_evidence.sh`](cpu_evidence.sh).

## Binary and input provenance

```
candidate  motioncorr          0d957e853f4c290aaa2dd098f36ff3c483096433c45c76a239fbdb76fec45215
candidate  image_write_faults  c7cde971ed9cac62e4704c5e5b466cc3a84504dbf1819d667d88c3fa91894b53
pre-fix    motioncorr          b9d16a2d8a69500c8ba8671382716a9cf79e851c2fa8264ed6735f2e3e5c82d8
pre-fix    image_write_faults  b01abcd4b01eea735ec10f64a30a5f49a6fcf11bce309b004ad4ae118111166a
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
in: src/rwMRC.h,  line 600  Failed to write image data (1048576 bytes) to …/big.mrc: File too large
in: src/image.h,  line 441  Failed to flush and close image file …/small.mrc: File too large
  destructor with an unflushable stream did not terminate
image write faults: ok
```

Two different files and two different detection points, by construction:

- `big.mrc` is 512×512, so the 1 MiB payload is larger than any stdio buffer and goes out
  through a direct `write(2)`. The short count reaches the **`fwrite` check** in `rwMRC.h`.
- `small.mrc` is 16×16, so header plus payload is 2 KiB and is still entirely in the stdio
  buffer when the last `fwrite` returns full success. Nothing has reached the fd. Only the
  **checked close** in `image.h` can see it. This is the case the issue singled out, and it
  fails if write counts alone are checked.
- The third line is the regression guard for the abort shown in §1.

The test also runs a healthy control that round-trips the payload, and a negative control
that repeats each fault with the limit lifted, so a passing assertion cannot be some
unrelated error being mistaken for the injected one.

## 4. Healthy output is unchanged

Same input, same arguments, same relative paths, pre-fix versus post-fix binaries:

```
mov/p.mrc                   neg=649e92e14f65ac35…  head=649e92e14f65ac35…   1049600 bytes
mov/p.star                  neg=18add2f32fe1708b…  head=18add2f32fe1708b…
corrected_micrographs.star  neg=89d486d7ebaa72ed…  head=89d486d7ebaa72ed…
```

Whole-file SHA-256, header included, not just the payload. A separate run under differing
output paths gave the same payload hash
`1a424122f6fd8f9b691197f92d9a6ca712458e9f51898e34232ad3ad271ce9d3`.

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

## 6. What is not claimed

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
