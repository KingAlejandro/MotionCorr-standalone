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
| D1 | complete corrected-image pixels | **24/24 images identical, 341,735,520 pixels compared** | **PASS** |
| D2 | full normalized MRC headers | included in the per-artifact comparison; no header difference outside the known auxiliary set | **PASS** |
| D3 | STAR inventory | **25 STAR artifacts compared**, all identical | **PASS** |
| D4 | per-movie exact gate | **24/24** | **PASS** |
| D5 | default-option invariance | the run uses default options; identical products | **PASS** |
| D6 | total artifacts | 109 compared, 105 pass, **4 fail** | see D7 |
| D7 | the 4 failures are the known PDF nondeterminism, preserved not suppressed | `all_batches.pdf`, `batch.pdf`, `header.pdf`, `logfile.pdf` — `identical_bytes=false`, `identical_normalized=false`, `kind=auxiliary`. This is the pre-existing ghostscript date nondeterminism already recorded on #66/#90. It is reported, not masked, and the overall grade is therefore `overall: FAIL` with `overall_graded: PASS` | **known, preserved** |
| D8 | ordered decoded-buffer control | serial decoded buffers compared between reference and candidate dumpers | see run log |

The `overall: FAIL` line is retained deliberately. Downgrading it to PASS would
require excluding the PDFs from the comparison, which is exactly the kind of
gate relaxation this task forbids.

## E. Findings this integration produced

| # | finding | severity | disposition |
|---|---|---|---|
| E1 | **Default CUDA configure fails** on this tree: `CMakeLists.txt:59` guards the `CMAKE_CUDA_ARCHITECTURES` fallback with `if(NOT DEFINED …)`, but `enable_language(CUDA)` has already defined it, so the fallback never fires. Reproduced fresh at head `d3c04f7`, configure exit 1. Pre-existing on main, **not** introduced here. README:53, `ci.yml` and both sbatch harnesses all pass `-DCMAKE_CUDA_ARCHITECTURES=80`, which is why it stays hidden | P2 | **Scoped build fix requested under #72/#18.** Deliberately NOT fixed on this branch — `CMakeLists.txt` is already carrying a four-way test-registration union here and a build-system change does not belong in the same reviewable unit. No broad CMake redesign proposed |
| E2 | **PR102's numpy requirement is a new hard build dependency on GPU hosts.** `BUILD_TESTING=ON` now `FATAL_ERROR`s without numpy. The 4-GPU VM has no numpy at all, so a CUDA `BUILD_TESTING=ON` configure that succeeded on main now fails. Measured: system `python3` has no numpy; the #69 thread's `BUILD_TESTING=ON` CUDA build succeeded on main minutes earlier | P2 | Arguably correct fail-closed behaviour — those tests genuinely need numpy — but it is a real new environment requirement that GPU-host workflows must satisfy. Worked around here with a local venv (`/home/alex/.mc-i96-venv`, numpy 2.5.3); recorded so the next GPU worker is not surprised. Not changed on this branch |
| E3 | **PR102's Control 3 Case B could not observe what it asserted** (count gate fired before the missing-name branch; the asserted substring came from the report's echo of the required list) | P2 | **Fixed on this branch**, commit `32620aa`, with an out-of-tree mutation control proving the repaired case detects a deleted missing-name check and the original does not |
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
