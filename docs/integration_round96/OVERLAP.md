# Semantic overlap analysis and recommended merge order

Base `4c952b3f`. Four groups integrated; two round96 PRs deliberately excluded.

## 1. File-level overlap actually encountered

| file | #72 / PR102 | #98 / PR101 | #92 / PR103 | #99 / PR105 | resolution |
|---|---|---|---|---|---|
| `CMakeLists.txt` | +11/−3 | +6 | — | +10 | **union of all test registrations** (see §2) |
| `src/image.h` | — | — | +136/−4 | +97/−18 | **genuine semantic merge** (see §3) |
| `src/motioncorr_runner.cpp` | — | +99/−12 | +54/−5 | — | disjoint hunks, auto-merged; verified the combined file carries both (§4) |
| `src/motioncorr_runner.h` | — | — | +8/−2 | — | no contention |
| `src/rwMRC.h`, `src/micrograph_model.cpp` | — | — | — | +86/−28, +7 | no contention |
| `src/rwTIFF.h` | — | — | +38/−15 | — | no contention |
| `WORKER_STATUS.md` | new | new (then deleted by the branch itself) | new | new | **archived per branch**, never dropped (§5) |
| `tools/validate_test_collection.py` | new | — | — | — | required-name inventory extended to the union (§2) |

`git merge` reported every one of these branches as `MERGEABLE` against main
individually. That is not the same as being composable, which is why §2–§4 exist.

## 2. CMake / test-inventory union

Main registers 13 CTests. The four groups add four more, and each group's
inventory names only its own:

| test | source group |
|---|---|
| `DefectParser` (+120 s timeout) | #98 / PR101 |
| `CiFailClosedControls` | #72 / PR102 |
| `WriteFaults` | #99 / PR105 |
| `ImageWriteFaults` (registered under `if(UNIX)`) | #99 / PR105 |

PR102 also replaced main's `if(Python3_Interpreter_FOUND)` guard with a
`find_package(... REQUIRED)` plus a numpy `FATAL_ERROR`. PR101 and PR105 were
both written against the *old* guarded structure, so taking either side
verbatim would have silently discarded the other's registrations. The resolved
`CMakeLists.txt` keeps PR102's structure and re-homes PR101's and PR105's
registrations inside it.

`tools/validate_test_collection.py` is the fail-closed inventory PR102
introduced. It is raised from 14 required names / `--min-count 14` to **17
required names / `--min-count 17`**. This is a tightening, not a relaxation.

**A defect was found in PR102's own control while doing this.** Control 3 Case B
claimed to prove that a missing required *name* is rejected, but fed a 13-name
collection to a validator whose count minimum was 14 — so the count gate always
fired first and the missing-name branch was never reached, while the asserted
substring appeared anyway because the report echoes the required-test list.
Verified against a copy of the validator with the missing-name branch deleted:

```
original Case B -> rc=1, assertion still satisfied   ("Test count 13 is less than minimum 16")  -> defect NOT detected
repaired Case B -> rc=0, assertion fails                                                        -> defect detected
```

The repair keeps the collection at the required count with an additive filler,
asserts the specific rejection reason, and covers all four integration-critical
names. See commit `32620aa`.

## 3. `src/image.h` — the one genuine semantic merge

Both #92 and #99 restructure `fImageHandler`.

- **#99** adds `writable` and `open_name`, rewrites `releaseHandles()` to flush
  writable streams and record the first `errno`, makes the destructor
  non-throwing, and widens the handle-reuse guard from `fimg && fhed` to
  include `ftiff` — which closed a pre-existing descriptor leak.
- **#92** adds a per-handle `tiff_err_ctx` and wraps `TIFFClose` in a
  `TiffErrorScope` so LibTIFF's close-time diagnostics reach that context
  rather than the process-global handler.

Three conflict hunks. The member and constructor hunks are additive and were
unioned. The third is a real decision:

| side | guard |
|---|---|
| #99 | `if (ftiff != NULL)` — wider; this is the leak fix |
| #92 | `if (isTiff && ftiff != NULL) { TiffErrorScope scope(...); ...` |

Resolved to the **wider guard plus the scope**, so the leak fix is retained and
the error context is entered for any live TIFF handle. `TiffErrorScope` only
saves and restores a thread-local pointer, so it is safe on the destructor path
that `releaseHandles()` also serves. The choice is commented in the source.

## 4. `src/motioncorr_runner.cpp` — verified, not assumed

#98 (defect-file parsing) and #92 (expected-frame-count propagation) both edit
this file and git auto-merged them. Auto-merge is not evidence, so the combined
file was checked two ways:

- the diff of the combined file against `pr/101` is exactly **+54/−5**, which is
  precisely PR103's own reported change to this file — i.e. the union and
  nothing else;
- both behaviours are present in the merged text, and both branches' tests pass
  on the combined tree (`DefectParser` 17/17 run, `DamagedMovie` 17/17 run).

## 5. `WORKER_STATUS.md`

Four branches create this root file. Resolving those collisions by picking one
would delete three workers' handoff records. Instead each is archived verbatim
under `docs/integration_round96/worker_status/` by a **pure rename commit**
after its group is applied, and the root file is reopened for this integration
job. PR101 deletes its own copy later in its history, so only three archives exist.

## 6. Not on this branch, and the edges they will hit

| PR | issue | why excluded | edge it must be integrated across |
|---|---|---|---|
| #100 | #97 recenter | changes option-on behaviour against inherited upstream code; needs explicit acceptance of the deliberate upstream-parity divergence plus option-on and non-one-`selected frames` controls | touches `src/motioncorr_runner.{cpp,h}`, which #98 and #92 already share here; it also adds a `runner_numerics` test case, so the inventory becomes 18 |
| #108 | #94 prefetch | out of scope by instruction | **largest edge.** It extracts the movie reader. It must carry #92's expected-count precedence *through* the refactored serial and prefetched paths, keep #99's checked handle lifetimes (the prefetch producer owns an `fImageHandler` on another thread, and `tiff_err_ctx` is per-handle while `g_tls_tiff_error_context` is thread-local — a handle opened on the producer thread and closed on the consumer thread restores the *consumer's* previous context), and not let a cancelled or failed decode publish success. Minimum tests it needs: identical decoded buffers serial vs prefetched for the same movie; expected-count rejection in both paths; a malformed/truncated TIFF retaining the correct movie/optics/exposure association under prefetch; producer-side write failure still failing the movie; non-prefix resume completing only the incomplete work. |
| #107 | #69 CUDA retry | out of scope by instruction | shares `src/motioncorr_runner.cpp` failure/ownership paths with #99's error publication; its retry must not republish a movie whose write already failed |
| #93 | #77 kernels | out of scope; overlaps #107 | pick one ownership model before stacking |
| #104 | #95 staging | unwired component, qualified NO-GO | none yet |
| #109 | #26 measurement | evidence only, measurement defects still being repaired | none |

## 7. Recommended merge order — smallest reviewed unit first

Each step is independently revertible and each is followed by a full-suite run
on the resulting tree, not on the branch in isolation.

1. **#72 / PR102** — CI and canonical fixtures. Zero `src/**` changes, and it is
   the gate everything after it is measured by. Merge it first so the following
   merges are checked by a trustworthy inventory. Carry the Control 3 repair and
   the inventory union from this branch (commits `32620aa`, `d3c04f7`), or the
   inventory will reject the very tests the next three steps add.
2. **#98 / PR101** — defect parser. Confined to one parse routine plus one test
   binary; its read-error fix is reviewed READY_TO_MERGE at `482c75ac`.
3. **#99 / PR105** — checked writes. Touches `src/image.h`, `src/rwMRC.h`,
   `src/micrograph_model.cpp`. Land **before** #92 so the `src/image.h` merge is
   resolved in the direction this branch validated.
4. **#92 / PR103** — TIFF integrity and expected frame count. Largest `src/**`
   surface of the four; lands last so a regression is attributable.
5. **#97 / PR100** — only after the upstream-divergence decision is recorded and
   its option-on evidence is complete. It is not part of this candidate.

Steps 1–4 are what this branch contains and validated together.
