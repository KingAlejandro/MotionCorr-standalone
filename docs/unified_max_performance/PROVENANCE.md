# Composition provenance — `experiment/unified-max-performance`

Base: main `6393547e6ed8a0fcbbda8fc314eb1ab7a969f709`.

Every production change imported into this branch is listed below with its
originating PR, the original commit, the composed commit that carries it, the
files it touched, and any manual reconciliation the coordinator performed.
Evidence-only and docs-only commits from those branches are **not** imported;
they remain on their own branches.

## Branch topology at dispatch

The CUDA branches are a stack, not independents. This is what made the
composition tractable and is worth recording, because the commit subjects
suggest otherwise:

```
main 6393547e
 └─ PR115 f9e90ef6   reliability / failure ownership
     ├─ PR118 081651fe   compact uint16 ingest
     │   ├─ PR125 1a297316   + owned host mapping  (#95 fix)
     │   ├─ PR122 1197bd5f   = PR118 + PR117
     │   └─ PR123 cfa331eb   = PR118 + tests only (src/ byte-identical to PR118)
     └─ PR126 629d1bc1   nvCOMP GPU Deflate     <-- branches from PR115, NOT from PR118
```

PR118 and PR115 appear to have divergent reliability lineages — duplicate
commit subjects `7572e3a`/`699fbcf` ("preserve enumeration failures across
recovery boundaries") and `5bda57c`/`1d533d2` ("…preprocessing disposal"). They
are not divergent. Nine of the reliability files are **byte-identical** across
PR115, PR118, PR125 and PR126:

| file | 115 | 118 | 125 | 126 |
|---|---|---|---|---|
| `cuda_error_class.h` | `4da54648` | = | = | = |
| `cuda_failure_state.h` | `72a34872` | = | = | = |
| `cuda_scoped_resources.h` | `d166aad6` | = | = | = |
| `cuda_alignpatch.cu` | `5c584b09` | = | = | = |
| `cuda_fft_prep.cu` | `aef449e1` | = | = | = |
| `cuda_fft_prep.h` | `97030a94` | = | = | = |
| `cuda_realspace_dw.cu` | `a104d976` | = | = | = |
| `motioncorr_runner.h` | `c722a8a9` | = | = | = |
| `cuda_movie_session.h` | `ee66d13b` | `4b5a4b11` | `4b5a4b11` | `fa68c77b` |
| `cuda_movie_session.cu` | `188070dc` | `8433a58e` | `8433a58e` | `dad3ae29` |

(first 8 hex of `git show <rev>:<path> | shasum`.)

So the whole three-way merge surface was three files:
`cuda_movie_session.h`, `cuda_movie_session.cu`, `motioncorr_runner.cpp`
(plus `CMakeLists.txt`, which merged without conflict).

**The nvCOMP fast path and the compact-U16 fallback have never coexisted on
any branch.** PR126 branches from PR115, so the routing between them is new
work in this composition, not an import.

## Imported production changes

| # | composed commit | origin | original commits | files | manual reconciliation |
|---|---|---|---|---|---|
| 1 | `6a3d125` | PR115 `f9e90ef6` | `94ef2ac f5ce15b 4369de1 0c13ce0 acb2f40 078ec54 7572e3a 5bda57c` | 12 src/CMake + 8 tests + 2 tools | none — file states taken verbatim, verified byte-identical to `f9e90ef6` |
| 2 | `e009238` | PR118 `081651fe` + PR125 `1a297316` | `05893e1 465d63f 07a0f6c 4adbd1d 8f08ea5 5278c39 fb0f653` | `cuda_movie_session.{h,cu}`, `motioncorr_runner.cpp`, `native_u16_staging.h`, 5 tests, 2 tools, CMake | none — PR125 carries the same reliability content, so the delta applied clean. Verified byte-identical to `1a297316` |
| 3 | `0b2642d` | PR126 `629d1bc1` | `f98d6ba 9b8ee0e f038e51 5eeb9a2 0ee7e5b b16c228 b39eee8` | `cuda_movie_session.{h,cu}`, `motioncorr_runner.cpp`, `cuda_deflate_layout.h`, `cuda_scratch_arena.h`, `defect_neighbours.h`, 3 tests, CMake, 2 tools | **yes — see below** |
| 4 | `a083a58` | PR125, PR115 | — | `docs/issue85_laneC/compare_output_trees.py`, `docs/issue69/evidence/ownership-20260929/compare-native.py` | two required CTest cases `importlib`-load these from `docs/`; composing only `src/ tests/ tools/ CMakeLists.txt` left them missing |
| 5 | `412e67d` | PR127 `a6a2ea69` | `c08fb29 b796441` + label half of `92e7662` + `29055c2` | `output_timing.h`, `image.h`, `time.cpp`, `metadata_label.cpp` | none |
| 6 | `83d3818` | PR127 | `cbf8dc7` (MRC half), `8ecc289` | `multidim_array.h` (stats only), `rwMRC.h`, `test_runner_numerics.cpp`, CMake, tools | split `multidim_array.h` by hunk so `takeBufferFrom` stays with the writer commit |
| 7 | `12a09db` | PR127 | `cbf8dc7` (PDF half), `18cb398`, `95c05a9`, `e363f45` | `CPlot2D.cpp`, `motioncorr_runner.cpp` (7 of 15 hunks), `test_pdf_concat.cpp`, CMake, tools | split the runner delta by hunk |
| 8 | `cfcd797` | PR127 | `92e7662`, `1e8d374` | `output_writer.{h,cpp}`, `multidim_array.h` (`takeBufferFrom`), `motioncorr_runner.{cpp,h}` | remaining 8 runner hunks; final state verified identical to the full three-way merge of PR127 into the composed tree |
| 9 | `5c72343` | new | — | `motioncorr_runner.{cpp,h}` | `--sync_output`, so the writer is ablatable without a second binary |
| 10 | `8fc63c6` | PR124 `082a8a46` | `082a8a46` (CMake + tests only) | `CMakeLists.txt`, `test_runner_numerics.cpp`, `test_tiff_read.py` | **yes — see below** |

Not imported, deliberately:

- every `docs/`-only and evidence-only commit on all ten branches;
- `tools/bench_ingest.cu`, `tools/microbench_tiff.cu` (PR126) — measurement
  tools, nothing in CMakeLists references them;
- PR124's `README.md` section and `docs/issue85_codec/**`;
- **PR121** persistent TIFF reader pool — a measured NO-GO. Its
  `src/rwTIFF.h` refactor changes the shipping single-threaded decode path and
  is not separable from the pool by cherry-pick, and its tests all construct
  `TiffMovieReader`. Nothing salvageable was importable without importing the
  feature;
- **PR109** operating-envelope study — measurement discipline only, no code;
- **PR122** — it is PR118 + PR117 with both duplicate reliability lineages
  merged in; superseded by composing from the sources directly;
- **PR123** — `src/` is byte-identical to PR118; only its test manifests are
  of interest and they are adapted rather than merged;
- **PR117** static multi-GPU workers — deferred until the one-worker candidate
  is accepted, per the dispatch;
- PR108 prefetch, PR93 cache work, mixed precision — explicitly out of scope.

## Manual reconciliation detail

### Commit 3 — nvCOMP over the compact fallback

Three-way merged with PR115 content as the base, PR125's composed state as
"ours", PR126 as "theirs". Five conflict hunks.

- `cuda_movie_session.h` (1 hunk) — adjacent insertion. Both sides add methods
  after `applyGainDefectsAndSum`. Kept both: the U16 overload, and
  `ingestCompressedTiffStrips` + `gatherFrameSamples`.
- `cuda_movie_session.cu` (1 hunk) — adjacent insertion. Kept
  `convertGainAndAccumulateU16Kernel` alongside `fusedU16FlipGainAndSumKernel`,
  the Adler-32 kernel and `gatherFrameSamplesKernel`.
- `motioncorr_runner.cpp` (3 hunks) — **structural, not textual.** PR126 moves
  the host read loop from before the CUDA session block to after it, inside
  `if (do_host_read)`, so the device ingest can replace it. PR125 branches
  *inside* that loop. Resolved to PR126's ordering with the compact arm folded
  in.

  The consequence is a deliberate predicate change. PR125 decided `stage_u16`
  before the session existed, so it approximated "a resident session will
  consume this" with `use_gpu && !early_binning`, and then had to widen the
  staged movie back to float when `initialize()` failed. In the composed
  ordering the session state is known first, so the predicate requires
  `movie_session` directly. That is strictly stronger, and it deletes the
  widen-after-failed-initialize path, which bound and released a movie-sized
  mapping for nothing. Products are unchanged: `(float)u16` is exact and the
  accumulation order is the same.

Everything else in that file merged automatically; the three regions where all
three paths meet — the gain-and-sum dispatch, the three-way defect-neighbour
loop, and the post-FFT release — were then read line by line and are recorded
as correct in the commit message.

### Commit 10 — PR124

`tests/test_runner_numerics.cpp` conflicted. PR124 was written against
`a75a3f87`, before #97 turned `main()` into a mode dispatch guarded by
`require(argc >= 2)`. PR124 reinstates a branch-wide `argc == 4 || argc == 5`,
which would reject the argument-free modes. Kept the composed dispatch and
gave `read_tiff_raw` its own argc check.

## Required-test registry

Recomputed as a union at every step, never copied from a branch.

| step | count | added |
|---|---|---|
| main `6393547e` | 20 | — |
| + #115 | 21 | `PatchRetryState` |
| + #118/#125 | 23 | `OutputTreeComparator`, `NativeU16Staging` |
| + #126 | 26 | `DeflateLayout`, `ScratchArena`, `DefectNeighbours` |
| + #127 A | 27 | `MrcHeaderStats` |
| + #127 B | 28 | `PdfConcat` |

PR126 registers `DeflateLayout`, `ScratchArena` and `DefectNeighbours` with
`add_test` but never added them to `DEFAULT_REQUIRED_TESTS`, so on that branch
the nvCOMP eligibility predicate and the arena bound could have been dropped
with the suite still green. Added here.

`tools/test_ci_fail_closed.py` restates the list by hand — deliberately, so
that a stale copy is detectable. Both copies are updated in the same commit at
every step and are asserted identical.

## Defects found and fixed after composition

None of these is an imported change. Each was found on the composed tree,
because composing is what made it reachable or observable, and each is listed
with the check that can see it.

| # | commit | defect | class | control |
|---|---|---|---|---|
| 1 | `06d158a`, `ac71b3f` | *(control: `sparse-recoverable` on the nvCOMP fixture, passing)* nvCOMP arm left **no valid representation** after a recoverable failure. `materialize_host_frames()` returns at its own first line on that arm, so a recoverable `updateDefectPixels` failure reached the CPU FFT with zero-size frames and `REPORT_ERROR` left an OpenMP region — `std::terminate`, killing the job. Four sites. | composition | **not written** |
| 2 | `b49b472` | Pinned budget enforced against the compressed payload, not the reservation: a 64 MiB cap pinned 96 MiB, an 8 MiB cap 32 MiB, per worker. | pre-existing (#126) | `DeflateLayout` |
| 3 | `b49b472` | `atol` cap parsing: `1G` silently became a 1 MiB cap that disabled the fast path for a whole run with no message. | pre-existing (#126) | `DeflateLayout` |
| 4 | `4aea2e6` | Patch-retry fallback gated on `host_frames_are_raw`, which the nvCOMP arm never sets, so `cudaPreparePatch` read `XSIZE == 0`. | composition | **still none.** `patch-prep-recoverable` exists but its injection site is not reached on the 48x40 control fixture, so it is held behind `--include-unproven` rather than shipped red. Needs a fixture on which `preparePatchInVram` actually runs |
| 5 | `4aea2e6` | `#pragma omp for` inside one arm of an if/else: a failing `TIFFOpen` skipped a barrier arrival and deadlocked the team. | pre-existing (#126) | `tiff-open-partial`, passing — falls back to the compact arm with complete products |
| 6 | `4aea2e6` | Ghostscript overlap: a throw from the main-thread `batch.pdf` pass unwound through a joinable `std::thread` — `std::terminate`. | pre-existing (#127) | `OutputStageFaults` |
| 7 | `95b4719`, `f5e564d` | CUDA-without-nvCOMP failed to link. `gatherFrameSamples` and then `endIngestScratch` were defined inside the guard and declared outside. The first stayed green only because the optimiser proved the call dead. | pre-existing (#126) | `NvcompGuards` |
| 8 | `cad4a29` | The ingest scratch teardown records failures **after** the return value is chosen, so a failed `cudaStreamSynchronize` was reported as a successful ingest. | pre-existing (#126) | `ingest-teardown-fatal`, passing — falls back to the compact arm with complete products |
| 9 | `1d13a4f`, `26f2273` | My own reconciliation errors, caught by `TiffRead` and by argparse. | mine | the tests that caught them |

Three of these are `std::terminate` or deadlock paths that end the whole job
rather than one movie, and all three were unreachable on the branches they came
from: #115's recovery paths assume a host movie that #126 removes, and #126's
guard mismatch is invisible until something gives the guarded symbol an
unguarded caller.

**Four of the nine have no automated control.** That is the branch's largest
remaining gap and is stated in each commit message rather than implied.

## Additions that are not imports

| commit | what | why |
|---|---|---|
| `5c72343` | `--sync_output` | PR127 constructs `OutputWriter(true)` unconditionally; ablating the writer would otherwise need a second binary, and any timing difference would carry every other difference two builds can have. |
| `89ec92f` | `--ingest auto\|nvcomp\|compact\|float`, `--ingest_witness` | IOParser treats an unknown flag as a *warning*, and PR126 deliberately removed its own log line for byte-exact log parity — so a benchmark arm could have run entirely on the host reader and looked identical. A pinned `--ingest` fails the movie when its path cannot be taken, so an arm proves which path it ran. |
| `cad4a29` | `MovieIngestStatus` | A bare bool conflated "no nvCOMP / unsupported encoding", "tried and failed, device fine" and "context dead" — and could not express a failure discovered after the value was chosen. |
| `78eccd5` | `--allow-added-log-line` | The candidate legitimately records which path ran. Suppressing the line would restore the unobservability; a log-wide waiver would hide real differences. Paired with two controls: the arm must fail *without* the allowance, and an ordinary log line mutation must still be rejected. |
| `f5e564d` | `tools/check_nvcomp_guards.py` | No test in the suite can see a guard mismatch, because the suite never links the configuration it breaks. |

## Required-test registry, final

| step | count | added |
|---|---|---|
| main `6393547e` | 20 | — |
| + #115 | 21 | `PatchRetryState` |
| + #118/#125 | 23 | `OutputTreeComparator`, `NativeU16Staging` |
| + #126 | 26 | `DeflateLayout`, `ScratchArena`, `DefectNeighbours` |
| + #127 A | 27 | `MrcHeaderStats` |
| + #127 B | 28 | `PdfConcat` |
| + writer fail-closed | 30 | `WriteFaultsSync`, `WriteFaultsMultiProduct` |
| + guard check | 31 | `NvcompGuards` |
| + PDF-stage fault | 32 | `OutputStageFaults` |

Both copies — `tools/validate_test_collection.py` and the hand-restated list in
`tools/test_ci_fail_closed.py` — are updated in the same commit at every step,
asserted identical, and every required name is checked to be registered in
CMakeLists.txt.

## Recovery-control status, measured

On SCARF `gnx002`, job 3515778, nvCOMP build:

| control | result | route taken |
|---|---|---|
| `unweighted-release-fatal` | PASS, refusal + cleanup attributed, 0 products | nvcomp |
| `dw-release-fatal` | PASS, same | nvcomp |
| `sparse-recoverable` | PASS, job survived, 3/3 products | nvcomp |
| `ingest-teardown-fatal` | PASS, job survived, 3/3 products | **fell back to compact** |
| `tiff-open-partial` | PASS, job survived, 3/3 products | **fell back to compact** |
| `patch-prep-recoverable` | **unproven** — injection site not reached on this fixture | — |

Each row asserts the outcome that matters and is common to all of them: the
fault fires, the job survives rather than dying, and the movie still produces
its complete product set. The internal route is printed, not asserted. An
earlier version asserted a route per row and failed on runs whose products
were perfect, because the code had taken a different and equally correct path.

Two of these rows only became meaningful once the pinned `--ingest nvcomp` was
removed from them: their correct outcome *is* a fallback, and pinning the
device path turns correct behaviour into a failed movie.

So five of the nine defects now have a passing control, and one -- the
patch-retry fallback -- still has none.
