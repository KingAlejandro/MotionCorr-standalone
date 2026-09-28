# Requirement → evidence matrix

Candidate source head: `d3c04f7f2a40637e8666ccfb4fb43a6e9540d316`
Base: `4c952b3f54479653512c4d208e09c9a8c02f3726`
Commits over base at that head: 49. Across the whole branch: **43 cherry-picked commits, every one retaining its original author** (40 by Alex Konstantinov, 3 by MotionCorr AI Assistant from PR103) each carrying an `(cherry picked from commit ...)` line, plus integration-authored commits prefixed `integrate(round96):` / `docs(integration):` / `evidence(integration):` / `docs(status):`. **No file present on base is deleted by this branch.**

Status vocabulary: **PASS** = executed on the combined candidate and observed.
**PASS (inherited)** = executed by the source branch on its own head, carried
here unchanged, not re-executed. **UNRUN** = not executed; no verdict claimed.
**N/A** = deliberately out of scope.

## A. Build and identity

| # | requirement | evidence | status |
|---|---|---|---|
| A1 | CPU Release build of the combined tree | cpu64, `-DCMAKE_BUILD_TYPE=Release`, cache shows `CMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG`, configure 0 / build 0, 0 errors, 5 warnings | **PASS** |
| A2 | build is not the unqualified `-O0` default | build type read back from `CMakeCache.txt`, not assumed | **PASS** |
| A3 | source identity is explicit | bundle sha256 `e448a71d…`, git tree `1c6d1efd…`, tracked-source digest `68aee5e5…`, working tree clean | **PASS** |
| A4 | binary identity is explicit | sha256 recorded for `motioncorr`, `runner_numerics`, `image_write_faults`, `defect_parser` | **PASS** |
| A5 | input identity is explicit | `movies.star` sha256 `fb998f70…`, 24-movie payload digest-of-digests `240fefa2…` | **PASS** |
| A6 | fresh CUDA compile, explicit `sm80` | 4-gpu-vm, configure 0 / build 0, **0 compile errors**, `libcudart.so.12` + `libcufft.so.11` linked, `cuobjdump --list-elf` shows `motioncorr.{1..4}.sm_80.cubin` — real device code, not a header stub | **PASS** |
| A7 | fresh CUDA compile with `BUILD_TESTING=ON` | configure 0 / build 0, 0 errors, 18 tests collected (17 + `CudaWrapperUploadFailure`), inventory check exit 0 | **PASS** |
| A8 | **default** CUDA configure validated separately | **configure FAILS: `CUDA_ARCHITECTURES is empty for target "motioncorr_core"`.** Reproduced fresh at this head. See §E1 | **FAIL, reproduced** |
| A9 | no stale CMake cache reused | every arm configures into a freshly `rm -rf`'d build dir from a fresh `git clone` of the bundle | **PASS** |

## B. Combined-source test suite

| # | requirement | evidence | status |
|---|---|---|---|
| B1 | full suite on the combined tree | **17/17 CTests pass**, `ctest` exit 0 | **PASS** |
| B2 | union of all four groups' test names registered | collected list contains `DefectParser`, `CiFailClosedControls`, `WriteFaults`, `ImageWriteFaults` plus main's 13 | **PASS** |
| B3 | no branch's test count summed in place of a combined run | this 17/17 is one run of one tree; the individual branches' 13/13, 14/14, 15/15, 40/40, 42/42 are **not** added together anywhere | **PASS** |
| B4 | suite re-run after each semantic group | groups 1–3 ran 16/16; group 4 (PR101) added `DefectParser` and the tree re-ran 17/17 | **PASS** |
| B5 | no gate, threshold or tolerance relaxed | inventory minimum raised 14→17; no numerical tolerance touched; `km_local_noisy` still executes and still reports FAIL, still excluded from aggregate acceptance | **PASS** |

## C. Negative controls — can the checks actually fail?

| # | control | expected | observed | status |
|---|---|---|---|---|
| C1 | required test `CiFailClosedControls` de-registered | inventory rejects | exit 1, names it | **PASS** |
| C2 | required test `WriteFaults` de-registered | inventory rejects | exit 1, names it | **PASS** |
| C3 | required script `tools/verify_fixtures.py` removed | preflight rejects | exit 1, `MISSING: tools/verify_fixtures.py` | **PASS** |
| C4 | one byte flipped in canonical fixture `km_global_hisnr.mrcs` | verification rejects, **after** an asserted clean baseline | baseline exit 0; after flipping offset 6291968 `0x86→0x87`, exit 1, same byte length so only the digest can catch it | **PASS** |
| C5 | **candidate's tests against BASE main source** | exactly the integrated groups' tests fail; everything else passes; the control must build and run | configure 0, **build 0**, ctest exit 8: **13/17 pass, 4 fail** — `DefectParser` (***Timeout 120.12 s*, the pre-#98 hang), `DamagedMovie` (#92), `WriteFaults` (#99), `ImageWriteFaults` (#99, *Subprocess aborted*). All 13 pre-existing tests pass unchanged | **PASS** |
| C6 | PR102's own Control 3 Case B is discriminating | must reject for the missing NAME | **defect found**: it rejected for the count. Repaired and re-verified by mutation — see `OVERLAP.md` §2 | **PASS after repair** |
| C7 | A/B comparator's own controls | missing file / altered pixel / altered header must each be detected | `controls_all_detected: true` for all three | **PASS** |

C5 is the load-bearing one: it is the only control that shows the integrated
production changes are what the new tests detect, rather than the tests being
green by construction. A control that fails to build detects nothing, so its
build exit is recorded.

## D. Healthy reference — exact current main vs the combined tree

All 24 tutorial movies, CPU backend, default options, `--j 8`,
`OMP_NUM_THREADS=1`. Reference binary built from a pristine `4c952b3`
worktree (`git status --porcelain` = 0 lines); binaries confirmed distinct by
sha256 before comparing, so the A/B cannot be a build against itself.

| # | requirement | observed | status |
|---|---|---|---|
| D1 | complete corrected-image pixels | **24/24 images identical, 341,735,520 pixels compared** — run twice, at the three-group head `6f29659` and again at the final four-group head `d3c04f7`, with identical results | **PASS** |
| D2 | full normalized MRC headers | included in the per-artifact comparison; no header difference outside the known auxiliary set | **PASS** |
| D3 | STAR inventory | **25 STAR artifacts compared**, all identical | **PASS** |
| D4 | per-movie exact gate | **24/24** | **PASS** |
| D5 | default-option invariance | the run uses default options; identical products | **PASS** |
| D6 | total artifacts | 109 compared, 105 pass, **4 fail** | see D7 |
| D7 | the 4 failures are the known PDF nondeterminism, preserved not suppressed | `all_batches.pdf`, `batch.pdf`, `header.pdf`, `logfile.pdf` — `identical_bytes=false`, `identical_normalized=false`, `kind=auxiliary`. This is the pre-existing ghostscript date nondeterminism already recorded on #66/#90. It is reported, not masked, and the overall grade is therefore `overall: FAIL` with `overall_graded: PASS` | **known, preserved** |
| D8 | ordered decoded-buffer control | serial decoded buffers compared between reference and candidate dumpers | see run log |
| D9 | A/B repeated at the final head after group 4 | identical: 109 artifacts, 105 pass, same 4 PDFs, `per_movie_exact_gate 24/24`, `controls_all_detected: true` | **PASS** |

The `overall: FAIL` line is retained deliberately. Downgrading it to PASS would
require excluding the PDFs from the comparison, which is exactly the kind of
gate relaxation this task forbids.

## E. Findings this integration produced

| # | finding | severity | disposition |
|---|---|---|---|
| E1 | **Default CUDA configure fails** on this tree: `CMakeLists.txt:59` guards the `CMAKE_CUDA_ARCHITECTURES` fallback with `if(NOT DEFINED …)`, but `enable_language(CUDA)` has already defined it, so the fallback never fires. Reproduced fresh at head `d3c04f7`, configure exit 1. Pre-existing on main, **not** introduced here. README:53, `ci.yml` and both sbatch harnesses all pass `-DCMAKE_CUDA_ARCHITECTURES=80`, which is why it stays hidden | P2 | **Scoped build fix requested under #72/#18.** Deliberately NOT fixed on this branch — `CMakeLists.txt` is already carrying a four-way test-registration union here and a build-system change does not belong in the same reviewable unit. No broad CMake redesign proposed |
| E2 | **PR102's numpy requirement is a new hard build dependency on GPU hosts.** `BUILD_TESTING=ON` now `FATAL_ERROR`s without numpy. The 4-GPU VM has no numpy at all, so a CUDA `BUILD_TESTING=ON` configure that succeeded on main now fails. Measured: system `python3` has no numpy; the #69 thread's `BUILD_TESTING=ON` CUDA build succeeded on main minutes earlier | P2 | Arguably correct fail-closed behaviour — those tests genuinely need numpy — but it is a real new environment requirement that GPU-host workflows must satisfy. Worked around here with a local venv (`/home/alex/.mc-i96-venv`, numpy 2.5.3); recorded so the next GPU worker is not surprised. Not changed on this branch |
| E3 | **PR102's Control 3 Case B could not observe what it asserted** (count gate fired before the missing-name branch; the asserted substring came from the `MISSING REQUIRED TESTS:` block, which prints whenever `missing` is non-empty — and `missing` is computed unconditionally at `validate_test_collection.py:73`, before either gate returns. Attribution corrected per independent code review P3-3; the finding itself is unchanged) | P2 | **Fixed on this branch**, commit `32620aa`, with an out-of-tree mutation control proving the repaired case detects a deleted missing-name check and the original does not |
| E4 | `tools/test_ci_fail_closed.py` Control 2 raises `FileNotFoundError` when `cmake` is absent from `PATH`, rather than failing with a diagnostic | P3 | Not changed — out of this integration's scope and it is a test-environment issue, not a product one. Recorded: the suite requires `cmake` on `PATH`, which GitHub CI provides and a bare cpu64 shell does not |
| E5 | C1/C2 (de-registering a required test at the CMake level) are dominated by the count gate: removing a test lowers the count, so the inventory rejects on count even though it also names the missing test | P3 | Accurate reporting only. The name check is isolated and proven by the repaired in-suite Control 3, not by C1/C2 |

## F. Explicitly UNRUN — no verdict claimed

| # | item | why | what would close it |
|---|---|---|---|
| F1 | **Any GPU execution of this candidate** | no execution slot assigned; instruction is explicit that native GPU whole-24 / option-on is required before any GPU integration claim but is not granted | `NEEDS_GPU` plan in the PR body |
| F2 | native CUDA all-24 healthy equality on the combined tree | F1 | one bounded 1-GPU run, UUID witness, per-movie product comparison |
| F3 | CUDA runtime behaviour of the `src/image.h` merge | F1. The TIFF error context and checked-write paths were compiled for `sm80` but never executed on a device | the same bounded run |
| F4 | #97 / PR100 recenter | conditional, excluded — see §G | its own controls plus the upstream-divergence decision |
| F5 | prefetch composition (#94 / PR108) | out of scope by instruction | the minimum test list in `OVERLAP.md` §6 |
| F6 | real older LibTIFF | inherited limitation of #92: the "compatibility" build forces the compatibility code path on the same modern 4.5.1 library | execution against an actually older LibTIFF |
| F7 | readable-shortened-TIFF detection | inherited, genuinely undecidable without an external authoritative count | unchanged; documented, not claimed |
| F8 | real ENOSPC / EIO / disk-full | inherited limitation of #99: `RLIMIT_FSIZE` exercises the real stdio and kernel path but is not disk exhaustion | unchanged |
| F9 | short **header** write injection | inherited from #99 and *measured* unreachable here: with `st_blksize` 4096 a 1024-byte header always fits the stream buffer | unchanged; covered in code, unrun as a distinct observation |
| F10 | libc++ / macOS defect-file read-error rejection | inherited from #98: libc++ reports the failed directory read as ordinary EOF, so the distinction is unrecoverable there. The regression probes the platform and does not count itself as coverage where it cannot observe | unchanged |
| F11 | scientific quality or downstream reconstruction | never in scope for a same-backend regression | independent-collection study (#73/#61) |

## G. Conditional / no-go rows

| item | verdict | reason |
|---|---|---|
| #97 / PR100 recenter fix | **CONDITIONAL — not integrated** | The fix is right about the inherited upstream defect, and its option-off controls preserve outputs exactly. But option-on changes 14,236,598 of 14,238,980 output pixels with max absolute difference 22.56. That is a deliberate divergence from the RELION `ad0b230` parity invariant this project holds itself to. Integrating it silently would convert a documented parity baseline into an undocumented one. Requires: (a) explicit recorded acceptance of the upstream-parity divergence; (b) option-on controls; (c) non-one `selected frames` coverage; (d) native CUDA option-on/off validation. **No scientific-quality improvement is claimed or implied by this row** — changed pixels are not better pixels |
| GPU integration claim for this candidate | **NO-GO for now** | F1–F3. CPU simulation is not a substitute and none was run as one |
| Default-CUDA-configure fix | **DEFER to #72/#18** | E1 |


## H. Independent review of the integration surface

Two bounded read-only reviewers, run against the final source head. Neither
compiled or ran anything; all execution evidence in this document is the
integrator's.

### H1. Code and specification — `READY_TO_MERGE`

No P1 and no P2 findings. Verified independently: the `src/image.h` merge
preserves both contracts with no swallowed error, no double-close and no leak;
`TiffErrorScope` save/restore is LIFO-safe because all four instances are
function-local automatics; `src/motioncorr_runner.cpp` is a true union with the
`expected_frames_*` vectors confirmed in lockstep with `fn_micrographs`;
`CMakeLists.txt` nesting is balanced and no registration was dropped; and the
Control 3 Case B defect claim was confirmed against PR102's own head `cf049ef`.
The reviewer also independently confirmed that `CMakeLists.txt:58`'s
`if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)` fallback is character-for-character
identical to base, so E1 is genuinely pre-existing and correctly deferred.

Two useful additions from that review:

- the widened `ftiff != NULL` case is in fact *unreachable* when `!isTiff`,
  because `ftiff` is only ever assigned on the `isTiff` branch. The widening
  therefore changes no diagnostic behaviour; it only closes the reuse leak;
- `releaseHandles()` also fixes a latent pre-existing UB in the base
  `closeFile()`, which could reach `fclose(fimg)` with `fimg == NULL` when
  `fhed != NULL && !isTiff`.

| finding | severity | disposition |
|---|---|---|
| P3-1 `INTEGRATED_SUITE` duplicates `DEFAULT_REQUIRED_TESTS` across two files | P3 | **Accepted, not fixed.** The reviewer traced all four drift permutations and every one fails loudly, so this is a maintenance burden and not a silent-green risk. Changing source after the review would invalidate the reviewed head for a nit. Recommended fix recorded for whoever adds test 18: import `DEFAULT_REQUIRED_TESTS` and derive the filler count from it |
| P3-2 `ImageWriteFaults` required unconditionally but registered under `if(UNIX)` | P3 | **Accepted, not fixed.** Linux and macOS both set `UNIX`; already flagged by an inline comment. Revisit only if Windows becomes a target |
| P3-3 attribution of the Control 3 defect was imprecise | P3 | **Fixed in the docs** above. The commit message of `32620aa` is immutable history and keeps the original wording |

### H2. License and scope — `LICENSE_COMPLIANCE_PASSED` + `SPEC_CONFORMANCE_PASSED`

`audit_licenses.py` exits 0 with verdict `LICENSE_WARNING` and 6 findings, **all
six pre-existing on base and untouched here** — confirmed by blob-OID identity
rather than by absence from the diff (`src/CPlot2D.{cpp,h}`, four AMD HIP
headers, `automation/requirements.txt`). No proprietary code, no ungranted
"All rights reserved", no non-commercial restriction, no new dependency surface.
numpy is BSD-3-Clause and already used by 10+ scripts at base.

Provenance: **43 cherry-picks, zero authorship rewrites**, verified on author
name, email *and* author date against each `(cherry picked from commit ...)`
original. The referenced originals are exactly the 43 commits on the four source
branches — bidirectionally complete, nothing dropped, nothing invented. PR103's
three `MotionCorr AI Assistant` commits retain their authorship with the
integrator as committer only.

All four worker handoffs are archived **byte-identically by blob OID**, and the
branch deletes nothing (`git diff --diff-filter=D 4c952b3..HEAD` is empty).
`docs/issue92_review_evidence/` (16 files) and `docs/issue99_write_faults/`
(6 files) match their source branches exactly.

That reviewer also flagged a methodology hazard worth repeating: a scripted
`git show pr/105:WORKER_STATUS.md | shasum` inside a loop with stderr suppressed
once returned the SHA-256 of the empty string, which would have read as a
spurious mismatch. It switched to blob-OID comparison, which cannot degrade that
way. A hash-of-nothing is exactly the shape of a green-looking check that
observed nothing.


## I. Review-follow-up round (28 Sep)

Codex review of `f9650704` raised one P2 on this branch: the canonical STAR
input was mutable. Confirmed by inspection and reproduced end to end.

| # | requirement | evidence | status |
|---|---|---|---|
| I1 | `--canonical` preserves the trusted committed STAR | generator compares and refuses; `git status` on `test-data/known_motion` empty after a canonical run | **PASS** |
| I2 | …or verifies its trusted digest before the gates | `star_sha256` added to the manifest schema (required), the manifest, and per-case verification; covers the `--no-regenerate` path that bypasses the generator | **PASS** |
| I3 | covers pixel-size / voltage / movie-reference mutation with unchanged pixels | Control 8B, three mutations on copies of the maintained generator | **PASS**, with a correction: see I7 |
| I4 | discriminating maintained-entrypoint negative control | Control 8: baseline, three mutations, disk-tamper bypass, legacy-manifest schema rejection | **PASS** |
| I5 | canonical movie/truth checks preserved | unchanged; Controls 4, 5, 7 still pass | **PASS** |
| I6 | test-registration union preserved | still 17 required names; Control 8 is a case inside `CiFailClosedControls` | **PASS** |
| I7 | **correction to the finding's framing** | `PIXEL_SIZE` is also passed to `write_mrc_stack()`, so it lands in the MRC header and **does** move `movie_sha256` (measured: `f9da4668…` → `c6c3f5b9…`). It was already caught. `VOLTAGE` and the movie reference are STAR-only and were genuinely silent. Only those two demonstrate the finding | recorded |
| I8 | before/after proof that the fix changes the outcome | VOLTAGE 300→200 on both heads, movie digest `f9da4668…` **equal to canonical on both**: reviewed head `f965070` → generator exit 0, STAR rewritten, `verify_fixtures` exit 0 reporting *"VERIFIED: 1 canonical fixtures match trusted manifest"* — **NOT DETECTED**. Fix head → generator exit 1, STAR untouched — **DETECTED** | **PASS** |
| I9 | composed suite at the final source | 17/17; negative control vs base `src/` fails on exactly the four integrated groups' tests | **PASS** (re-run at the composed head) |
| I10 | native CUDA baseline on a dedicated allocation | SCARF job `3511126`, own exclusive allocation and own dataset copy | see §J |

### A control of mine that could not observe what it asserted

The first version of Control 8 asserted a `PIXEL_SIZE` mutation was *not*
detected by the movie digest, and passed — but only because the STAR check ran
first and raised before the movie check was reached. The assertion was
structurally incapable of failing. Found by measuring rather than reasoning,
corrected in `fe8ca55`, and the before/after arm had the same flaw (it inferred
detection from a bare exit code) and was corrected with it. Recorded because a
green control that observes nothing is the precise failure mode this branch
exists to remove.

An earlier negative-control run also reported 5 failures rather than 4. The
fifth was Control 6, and the cause was the harness: `verify_fixtures.py` reads
the manifest from `git:HEAD` by design, the throwaway worktree was detached at
base, and base's manifest predates `star_sha256`. Committing the candidate
tooling onto the detached HEAD fixed the harness; the count returned to 4. It
also pins a real constraint — `verify_fixtures.py` and `MANIFEST.json` must land
in one commit, which they do.


## J. Native CUDA baseline — RUN (supersedes the F1–F3 unrun rows)

Alex authorized parallel GPU acceptance on 28 Sep. Two independent native
executions were performed; neither is a compile.

### J1. Dedicated SCARF allocation — job `3511135`

Partition `gpu-devel`, exclusive node `gn3001`, A100-SXM4-40GB, own dataset copy
under `pr110-baseline/data`. Head `07a6a777`.

> Partition `gpu` carries QoS `limitgpunodes` with `MaxJobsPU=1`, held by #94, so
> the first submission (`3511126`) sat on `QOSMaxJobsPerUserLimit`. `gpu-devel` is
> a separate QOS with idle nodes — a genuinely distinct allocation, not a share of
> #94's. Job `3511126` was cancelled by me; no other task's job was touched.

**Execution witness, sampled while the run was on the device:**

```
pid 410748  .../cand/build/motioncorr  428 MiB  GPU-c7b9c523-f18f-6873-d6d1-d080c2489e8f
GPU-c7b9c523...  30 % util, 439 MiB      other three devices: 0 %, 4 MiB
```

| arm | exit | wall | peak RSS | products |
|---|---|---|---|---|
| main `4c952b3` | 0 | 28.14 s | 1 610 960 kB | 24 |
| candidate | 0 | 27.92 s | 1 609 476 kB | 24 |

### J2. Shared VM GPU3 — **USER-AUTHORIZED EXCEPTION to the published envelope**

**Final standing.** This run was authorized by Alex directly and is not an
unauthorized action or a worker fault. The labelling went through three states
and all three are kept visible rather than overwritten:

| when | what |
|---|---|
| **2026-09-28T07:22:00.189Z** | Alex's direct user message: *"Run on 4GPU as well"* — the grant |
| 07:25:04Z → ~07:30Z | the run executed, wholly after the grant |
| later | a coordinator message called it out-of-envelope; §J2 was relabelled accordingly |
| later still | the coordinator **retracted** that warning, confirming the grant from read-only history and directing that it be recorded as a user-authorized exception |

The published envelope (GPU3 unallocated, aggregate 24 logical CPUs at 96-119)
was the standing policy; the user grant supersedes it for this bounded run. The
extension was flagged in the commit message, the PR comment and the status file
at the time rather than taken quietly.

**Actual use, occupancy and budget:**

| | |
|---|---|
| device | GPU3 only, selected by **UUID** `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` — ordinals never identify silicon |
| pre-flight | aborts if GPU3 has any compute app; observed all four devices at 1 MiB / 0 %, no compute apps, no MotionCorr processes, load 0.26 |
| CPUs | 120-123 (4 logical, NUMA node1, no SMT), inherited `Cpus_allowed_list: 120-123` verified in-job |
| disjointness | **#53's GPU0/1 + CPUs 96-111 and #69's GPU2 + CPUs 112-119 were never touched**; witness during the run shows the other three devices at 0 % / 1 MiB |
| build / runtime | `-j4`, `OMP_NUM_THREADS=4` |
| lock | own device lock `/tmp/motioncorr-gpu3-pr110.lock`; the benchmark mutex deliberately **not** taken, because this is correctness and not timing |
| colleagues | no llama, colleague process or service altered; none present |
| release | device and lock released on completion — verified free afterwards: all four devices 1 MiB / 0 %, no compute apps, lock not held |
| claims | correctness only. **No timing is claimed** from a shared box, and SCARF and VM results are never combined into one curve |

**Artifacts preserved exactly as produced**, under
`docs/integration_round96/evidence/vm-gpu3/` and on the VM at
`/home/alex/mc-pr110-gpu3` (2.7 GB). No raw evidence was rewritten at any point
in the three labelling states, and no run was restarted for wording.

**Independence.** §J1's dedicated SCARF baseline is the native evidence of
record and can be assessed entirely on its own. Strike this section and §J1 is
unchanged — that separability was true when this was thought to be
out-of-envelope and remains true now.

### J3. Result — the SCARF baseline, independently corroborated on the VM

The SCARF column is the evidence of record and stands alone. The VM column is a
**user-authorized** second platform; it corroborates but is not required.

| | SCARF gn3001 (**of record**) | VM GPU3 (user-authorized, corroboration) |
|---|---|---|
| images pixel-identical | **24/24** | **24/24** |
| total pixels compared | **341,735,520** | **341,735,520** |
| per-image RMSE / max abs | 0.0 / 0.0 | 0.0 / 0.0 |
| core header diff bytes | 0 | 0 |
| normalized label diff bytes | 0 | 0 |
| STAR artifacts identical | **25/25** | **25/25** |
| differing | 21 `.log` + 4 PDFs | 24 `.log` + 4 PDFs |

The pixel count equals the cpu64 lane's exactly, so native and CPU cover the
same complete product surface. The `.log` differences are measured GPU timing
only — e.g. `Total GPU alignment time: 114.33 ms` vs `9.21 ms`, `cuFFT execution
time: 1.05 ms` vs `1.04 ms` — with the per-movie STAR beside them byte-identical.
**The four PDF differences remain, and the overall verdict is still not green on
them.**

### J4. Native controls — job `3511136`

| control | result |
|---|---|
| C1 decoded-reader, `--j 1` vs `--j 8`, same device | **24/24 pixel-identical**, rmse 0.0, normalized label diff 0 |
| C2 truncated TIFF | exit 1; *"failed for 1 movie"* — exactly the damaged one, named 5×; healthy `.mrc` retained; **joint STAR withheld** |
| C3 resume after repair | exit 0; 2 of 2 products; joint STAR now present; healthy movie **pixel-identical** (untouched by the resume); repaired movie **pixel-identical** to the full healthy run |

### J5. Three harness defects found and fixed, none a product defect

Recorded because each produced a confident-looking wrong answer:

1. The first comparison reported **78 failing artifacts**. It hashed `.mrc`
   whole-file, and the MRC label is timestamped —
   `label_header_diff_bytes=3`, `normalized_label_diff_bytes=0`. It also passed
   `--require-complete-coverage` without the STAR pair, so the comparator failed
   on missing `motion_and_star` coverage and returned 1 for a pair whose image
   parity was exact.
2. `total_pixels_compared: 0` — the JSON keys were guessed. The real schema is
   `checks.corrected_image.*`; the 341.7 M figure exists only because that was
   fixed.
3. The damaged-movie sandbox filtered `movies.star` with a rule that never
   matched (data rows carry a trailing optics-group column), so 22 movies were
   legitimately absent and "resume failed" was the sandbox, not the product.

### J6. Still not claimed

Neither run is a timing study, a CPU/CUDA agreement claim, a RELION parity
claim, or a scientific-equivalence claim. The VM run in particular shares a box
and is correctness-only. `km_local_noisy` still FAILs and is still excluded from
aggregate acceptance. The default CUDA configure failure (§E1) and the numpy
build dependency (§E2) are unchanged and still open.


## K. Residual decision raised by the delta audit: `generator_sha256`

`test-data/known_motion/MANIFEST.json` records
`generator_sha256: cf4f2aeb…`, which is the generator as of base `4c952b3`. The
file has since changed twice — once by PR102's staging restructure and once by
this branch's STAR-immutability fix — so it is now `16b26f86…`.

**Deliberately not changed here.** The field is ambiguous and the two readings
point opposite ways:

- *"the generator that produced these recorded digests"* — then `cf4f2aeb…` is
  **correct** and updating it would falsely claim the current script produced
  the committed fixture bytes;
- *"the generator currently in the tree"* — then it is stale.

Rewriting a trust-anchor field on a guess is the kind of quiet alteration this
branch exists to prevent, so the reading is left to #72, which owns the file.

**It is not a correctness hole either way**, and this is the substantive point:
nothing reads `generator_sha256` (`grep` over `tools/` and `.github/workflows/`
finds no consumer), and the property it gestures at is already established
empirically on every CI run. `--canonical` re-derives each movie from the
current generator and compares against the recorded `movie_sha256`, so a
generator that no longer reproduces the canonical bytes fails the run outright.
The digest field is documentation; the regeneration check is the gate.

The delta auditor was right to flag it as *"an unchecked provenance field
drifting silently … the shape of a guard that cannot observe what it asserts."*
The options for #72 are: validate it, drop it, or document its meaning. Any of
the three is better than leaving it undefined, and none belongs in an
integration branch.
