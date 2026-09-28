# ADR — issue #99: fail-closed MRC image writes and completion (PR A)

| Field | Value |
|---|---|
| Issue | [#99](https://github.com/KingAlejandro/MotionCorr-standalone/issues/99) — make MRC output write failures fail closed and prevent false completion |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Branch | `round96/99-claude-opus-5` |
| Scope | PR A only — reproduce, then propagate. PR B (publication/identity semantics) is deferred, see §7. |
| Related | #66 lane A, #96 audit index, #90 (direct matching-type write), #91 (per-movie failure isolation), #69 (GPU failure/retry), #85 (write performance) |

---

## 1. Ownership chain, as it actually is at 4c952b3f

This is the trace the issue asks for before any API change. Line numbers are at the base commit.

```
MotioncorrRunner::run()                                  src/motioncorr_runner.cpp:577
  └─ try { executeOwnMotionCorrection(mic) }                                    :611
       └─ Iref.write(fn_avg, -1, false, WRITE_OVERWRITE, …)      :2446 :2455 :2456 :2547
            └─ Image<T>::write()                                       src/image.h:564
                 ├─ fImageHandler::openFile(name, mode)                         :231
                 │    └─ fopen(...)                     — checked, REPORT_ERROR :328
                 ├─ Image<T>::_write(...)                                      :1464
                 │    └─ writeMRC(select_img, …)      — RETURN VALUE DISCARDED :1567
                 │         ├─ fwrite(header, 1024, 1, fimg)   — UNCHECKED  rwMRC.h:502
                 │         ├─ fwrite(MULTIDIM_ARRAY(data), …) — UNCHECKED       :513
                 │         ├─ fwrite(fdata, …)                — UNCHECKED       :529
                 │         ├─ fseek(...)                      — UNCHECKED  :534 :537
                 │         └─ fwrite(fdata, …) (stack loop)   — UNCHECKED       :543
                 └─ ~fImageHandler()                                            :226
                      └─ closeFile() → fclose()                                 :359
                           — checked, but REPORT_ERROR *from a destructor*
  └─ catch (RelionError &) → failed_movies.push_back(...)                       :626
  └─ if (!failed_movies.empty()) REPORT_ERROR(...)   — withholds joint outputs  :641
  └─ generateLogFilePDFAndWriteStarFiles()           — reached only on success  :650
```

Two distinct defects fall out of that trace, and they need different fixes.

### Defect 1 — the writer cannot report a short write at all

Every payload and header `fwrite` in `writeMRC` discards its return value, and `_write`
discards `writeMRC`'s return value on the MRC branches (`writeSPIDER` is assigned to
`err`; `writeMRC` is not). A short or failed write therefore returns 0 = success all the
way out of `Image::write()`. `executeOwnMotionCorrection` returns `true`, `saveModel`
writes the per-movie STAR, the movie never reaches `failed_movies`, and the job exits 0
having published a joint STAR that points at a truncated micrograph.

### Defect 2 — the one place that *does* check cannot report either

stdio buffers. A `fwrite` that returns its full item count has not necessarily reached the
filesystem; ENOSPC/EDQUOT/EIO can surface first at flush time. In this chain the only
flush is `fclose` inside `~fImageHandler`, and its failure path is `REPORT_ERROR`, i.e.
`throw`. Destructors are implicitly `noexcept` in C++11, so that throw is not an error
report — it is `std::terminate`. The process dies on SIGABRT with no named file, which is
the same class of batch-wide failure that #91 fixed for damaged *inputs*. `closeFile()`
also leaves `fimg` non-NULL on the failing path, so the destructor can double-close.

Consequence: **no code path in the current source can turn a failed image write into a
per-movie failure.** Either it is silent (defect 1) or it is fatal to the whole batch
(defect 2).

### What is already correct, and is therefore not re-implemented here

- #91 already isolates per-movie failure, names the movie, retains healthy products and
  withholds the joint STAR/PDF (`run()` :596-648). PR A only needs to *raise* into it.
- `isMovieComplete`/`completeMrc` (:509-575) already reject a truncated MRC on resume by
  comparing the declared geometry against the file length, and already validate the STAR
  shift block. PR A adds no resume logic; it adds a test that pins this behaviour.
- `openFile` already checks `fopen`.

## 2. Decision

Three changes, each the smallest that makes one link in the chain observable.

**D1 — `writeMRC` checks every write and seek, and names the product and stage.**
A private `mrcWriteBlock()` helper returns an empty string on success and a diagnostic
(path, stage, byte count, `strerror`) otherwise. The caller accumulates the first
diagnostic, then unlocks the file and frees `header`/`fdata` on the failure path exactly
as on the success path, and only then throws. `fseek` for the APPEND/REPLACE branches is
checked the same way.

**D2 — `Image::write()` closes explicitly, so a deferred flush error is observable.**
`fImageHandler` gains `releaseHandles()`, which flushes writable streams, records the
first `errno`, and closes and nulls every handle unconditionally. `closeFile(name)` wraps
it and throws with the product path. The destructor calls `releaseHandles()` and ignores
the result — it can no longer terminate the process, and it can no longer double-close.
`Image::write()` calls `closeFile(fname)` after `_write` rather than leaving the flush to
the destructor. Read paths keep relying on the destructor and are not flushed
(`writable` is recorded at `openFile` time), so no read behaviour changes.

**D3 — `Micrograph::write()` checks the stream.** The per-movie `.star` is the de-facto
completion marker consulted by `isMovieComplete`; a silently truncated one is the same
false-completion bug in the metadata half of the product set. Four lines: check
`fh.fail()` after `close()` and report the path.

`_write` additionally assigns `writeMRC`'s return value to the existing `err` variable, so
the already-present `if (err < 0)` guard is live rather than dead on the MRC branches.

### Explicitly not done in PR A

No `fsync`, no `O_DIRECT`, no temporary-path-and-rename, no transaction framework, no
manifest, no completion-identity hashing, no change to any numerical gate, output default,
CUDA arithmetic or the #90 direct matching-type write. PR A does not remove the truncated
file it leaves behind; §7 explains why that is safe today and what PR B owes.

## 3. Durability semantics claimed (and not claimed)

PR A claims exactly this: **if the C library or the kernel reports an error for any write,
seek, flush or close performed by this process for a requested image product, that movie
fails, is named, and produces no completion record.** It does **not** claim the bytes of a
successfully reported write are durable across a machine crash — that needs `fsync` and a
measured requirement, which #99's own comment defers. Errors that the filesystem only
reports to a *later* writer (some NFS client configurations report write-back errors on
`close` only to the fd that dirtied the page — which this process owns — but a few report
them nowhere) remain out of reach of any fix that does not `fsync`.

## 4. Fault injection: why `RLIMIT_FSIZE`, not `LD_PRELOAD` and not a real disk

The issue requires deterministic short/failed writes and forbids filling a shared disk.

- `LD_PRELOAD`/`--wrap` interposition is Linux-only (the repo already restricts
  `cuda_wrapper_upload_failure` to Linux for this reason) and interposes the wrong layer:
  wrapping `fwrite` skips the real buffering, which is precisely the behaviour under test.
- A writer test double would replace `writeMRC`, so it could not observe defect 2 at all.
- `setrlimit(RLIMIT_FSIZE, n)` makes the *real* stdio and *real* kernel write path fail at
  a byte offset we choose. It is POSIX, needs no privileges, touches no shared disk, and is
  exactly reproducible. `SIGXFSZ` is set to `SIG_IGN`, which is inherited across `execve`,
  so the same lever works for an out-of-process end-to-end test.

Choosing the limit selects which defect is exercised, which is the point:

| limit vs. product | what stdio does | which check must catch it |
|---|---|---|
| below header+payload, payload larger than the stdio buffer | `fwrite` issues a direct `write(2)`, gets a short count then `EFBIG` | D1 payload check (`fwrite` returns 0) |
| below header+payload, whole product smaller than the stdio buffer | both `fwrite`s buffer and report success; nothing has reached the fd | D2 close check only |

The second row is the case the issue singles out: *"a buffered `fwrite` can appear
successful before a later flush fails, so checking only its count is insufficient"*. It is
a real test of D2 and it fails if only D1 is implemented.

## 5. Tests

- `tests/test_image_write_faults.cpp` (new CTest `ImageWriteFaults`, links
  `motioncorr_core`, no fixture, sub-second):
  1. healthy control — write succeeds, file length and payload bytes exact;
  2. short payload write — 512×512 float MRC under a 600 000-byte limit; expects a throw
     naming the path and the `image data` stage, caught by D1;
  3. delayed flush/close failure — 16×16 float MRC under a limit between header and
     header+payload; both `fwrite`s succeed, expects a throw naming the path, caught by D2
     alone;
  4. negative control — the same fault with the limit lifted must not throw, proving the
     assertions in (2) and (3) are observing the injected fault and not an unrelated error;
  5. destructor safety — the failing handle is destroyed after the throw without
     `std::terminate`, which is the regression guard for defect 2's old behaviour.
- `tests/test_write_faults.py` (new CTest `WriteFaults`, end-to-end on the existing
  synthetic TIFF; movie A healthy first, then A+B under a file-size limit with
  `--only_do_unfinished`, then repaired retry):
  - the failing run exits non-zero and is *not* killed by a signal;
  - stderr names the failed movie and the output product path;
  - A's `.mrc` and `.star` bytes are byte-identical before and after the failed run;
  - B has no `.star` completion record and its truncated `.mrc` is rejected by
    `isMovieComplete` (proved by the repaired retry reprocessing it);
  - the joint `corrected_micrographs.star` is not updated to contain B;
  - the repaired retry exits 0, leaves A untouched, and publishes a joint STAR with both.
- Regression: the existing CPU CTest set must stay green, and `SyntheticRegression` pins
  that healthy MRC bytes are unchanged by D1/D2.

## 6. Changed-file whitelist

| File | Kind | Change |
|---|---|---|
| `src/rwMRC.h` | production | D1: `mrcWriteBlock` helper; checked header/payload/seek; unlock+free on the failure path |
| `src/image.h` | production | D2: `fImageHandler::{writable,releaseHandles,closeFile(name)}`, non-throwing destructor, explicit close in `Image::write`, `err =` on the `writeMRC` branches |
| `src/micrograph_model.cpp` | production | D3: check `fh.fail()` in `Micrograph::write` |
| `tests/test_image_write_faults.cpp` | test | new |
| `tests/test_write_faults.py` | test | new |
| `CMakeLists.txt` | test | two `add_test` entries plus one `add_executable` |
| `agents/designs/issue_99_fail_closed_image_writes.md` | docs | this ADR |
| `WORKER_STATUS.md` | docs | handoff status |
| `docs/issue99_write_faults/` | docs | executed evidence |

Nothing under `src/motioncorr_runner.cpp` is touched: the per-movie failure contract it
needs already exists from #91, and #97/#98/#69 hold the other locks on that file.

Correction from the independent spec review: `src/micrograph_model.cpp` is *not* free of
sibling overlap. #98's SerialEM defect-text detection runs from
`Micrograph::fillDefectAndHotpixels` in that same file. The D3 edit is +7 lines at the
end of `Micrograph::write`, roughly 50 lines away and semantically unrelated, so the
collision risk is textual rather than semantic — but the file is shared and should be
merged in that knowledge.

## 7. PR B (deferred, designed but not implemented here)

PR A leaves a truncated `.mrc` on disk after a failed write. That is safe *today* only
because `completeMrc` length-validates it on resume and nothing else consumes an output
whose movie failed the batch. It is not safe in general, and it is not a completion
*publication* design. PR B, to be designed with #53/#67 before implementation, owes:

1. collision-safe temporary product paths, with the completion record published last —
   noting that renaming one MRC does not atomically commit a DW/noDW/EVN/ODD/PS/model set,
   so the record, not the rename, is the commit point;
2. an explicit statement of the supported filesystem and durability semantics, including
   whether `fsync` is required, backed by a measurement rather than a blanket per-frame
   flush;
3. completion identity over input/gain/options/requested-product-set, with a stated I/O
   cost and trust model and a compatibility policy for outputs written before the scheme,
   so stale-but-readable results are not silently skipped after inputs change;
4. the remaining acceptance cases from the issue that PR A does not cover: cancellation
   during output, per-product failure across the full product matrix, and changed
   gain/options.

PR A is independently useful without any of it: it converts a silent truncation into a
named per-movie failure, which is the property the issue's acceptance criteria lead with.
