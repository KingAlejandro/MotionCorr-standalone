# PR287 local CCF capture — independent source review r1 (Opus 5.5, HIGH)

Reviewed: source 927a6890c8864f81ad58e44eac7281b080714af4 vs base edda006253aaac8f84e177dcf10f6502e7342df2,
plus the CMake guard in ea775cc5 (CMakeLists.txt identical at ce5f5844) and docs-only ANALYSIS_PROTOCOL.md at ce5f5844.
src/ and tests/ are identical 927..ce5f5844 (git diff --quiet). Blob hashes: source927-blob-sha256.txt.
Read via git objects only; the root checkout (c884) and the advancing worktree files were not used.

## Verdict

No material or blocking production or capture-correctness finding. The author may run the two
already-authorized tiny OFF/ON identity producers once their own build/tests pass under fresh leases.
This review does not clear broader native qualification, adoption, or any scientific claim.

## What was checked (source/static only)

- Flag-off path: env unset -> diag_local_ccf_dir empty -> capture_session null -> every `capture` pointer
  null. The OFF branch keeps the original `inverseFourierTransform(Fccs, Iccs())` call; the only added
  work is the null check in `_inverseFourierTransform`. Defaults FwdOnly/preserveInput=true match the
  capture branch's explicit arguments. Planned-float and double overloads pass the default nullptr
  observer and are unchanged. Plans are FFTW_ESTIMATE|FFTW_UNALIGNED and cached per alignment class,
  so capture-induced heap changes cannot change the plan algorithm. Source review cannot establish
  bit neutrality; the OFF/ON producers remain required.
- Observer brackets the actual `fftwf_execute_dft_c2r`; with preserveInput it receives the clone `src2`
  (actual temporary), distinct from the API argument snapshots (pre-DC, post-DC, API-after).
  Destroyed temporary allowed nonfinite; everything else fails closed on nonfinite.
- Geometry pins verified from code: B=150, prescaling=1 -> requested scale 0.248 -> findGoodSize(10)=192
  -> capped to 42x32; search_range 50 -> 20 -> 15. Patch bounds for 128x96, 3x3: ix=1 -> x [42,84),
  centre 62; iy=1/2 -> centres 47/79. Native (2,2)/(3,2) labels match.
- Threading: clipped() in the igroup OMP loop and preDc/postDc/observer/peak/result in the iframe OMP
  loop each touch only frame[index]; vectors preallocated in configure()/constructor, no allocation or
  IO in callbacks (all noexcept, no throwing calls). All file writes and all throwing calls are in
  serial code (constructor, configure, begin, rawResults, end, finish, reported, session finish),
  never inside an OMP region. frame vector is never resized, so observer pointers stay valid.
- State: reset() per iteration clears before/after/filled/bad/verdict/coupled offsets; coupled offsets
  are copied only when verdict==0 and serialized as null otherwise; native separable fallback and
  raw/scaled shifts are recorded unclipped. posx/maxval/separable/raw/scaled are written
  unconditionally every frame before result() sets filled.
- Recomputed window/sum-of-others/raw-product use the native ly mapping and the same float operation
  order as the native expression (before the weight multiply); labeled as recomputation.
- peak3x3 wrap, tie rule (strict >, y outer, x ascending), equality tie count, Hermitian residual
  columns (x=0 and x=21 of 22, partner row (ny-y)%ny) are consistent with the native layout.
- File naming has no collisions across stages/iterations; O_CREAT|O_EXCL (also refuses symlinks),
  short-write loop, close checked, 64 MiB shared cap checked before open (~3 MB expected for
  2 patches x <=5 iterations).
- Guards: capture guard runs in read() at line 262, before the existing --gpu experimental refusals
  (441+) and before any STAR/movie access; session root created only after header parse, before gain
  and pixels. Guard matches the sealed factorial command (use_own, j2, bin1/group1, skip_defect,
  first1/last5, default max_iter 5 and B 150) plus UP flags (coupled all, DC arm both).
- Failure path: capture errors are std::runtime_error / filesystem_error, which bypass the per-movie
  `catch (RelionError&)` and reach main's `catch (std::exception&)` -> RELION_EXIT_FAILURE. All product
  submissions (runner927 line 4314+) follow capture_session->finish() (line 4025), so no per-movie
  product is queued before a capture failure. Consistent with the design ("abort before normal
  publication"); when OFF, failure/publication behaviour is unchanged.
- CMake guard (ea775cc5): LocalCcfCaptureCli registered only under option MC_EXPERIMENT_CCF_DC (same
  name as line 157). Correct: a non-DC build refuses with "requires the DC diagnostic build", which
  would not match the test needles.
- License: new files carry SPDX GPL-2.0-or-later; existing headers untouched; no new dependencies.
- ANALYSIS_PROTOCOL.md (ce5f5844) only uses arrays the capture provides; no source implication.

## Low notes (non-blocking)

1. tests/test_local_ccf_capture_cli.py has refusal cases only. An always-refusing guard would pass it,
   and the failure would first show up in the ON producer (one of the two budgeted runs). Cheap fix:
   add a positive case: base config with the absent STAR must exit nonzero without any
   "MC_DIAG_LOCAL_CCF_DIR" message, and with no capture root (STAR read fails before the session).
2. tests/test_local_ccf_capture.cpp "observer did not receive actual C2R input" compares the pre-C2R
   snapshot to the original. With preserveInput the clone and the API argument are bit-equal, so a
   mutant passing the API argument would pass. Adding `observer.temporary_after != bits` would show
   the observer saw the destroyed temporary. Source inspection confirms the implementation passes
   the clone.
3. pre_dc/post_dc have no presence flags; completeness relies on their unconditional placement in the
   same OMP body as the observer/result calls. Correct at 927; would become stale if those calls were
   later made conditional.
4. Cosmetic: errno is read in the same expression that builds the message string in exclusiveFile's
   open failure path; the message could show a wrong errno. No effect on fail-closed behaviour.

## Tests performed and limits

- Performed: static source review of the exact 927 diff and surrounding runner/new_ft code, ea775cc5
  CMake delta, ce5f5844 docs delta; blob hashing. No compilation, no tests, no native/movie/GPU job,
  no remote compute.
- UNRUN by this reviewer: build, LocalCcfCapture, LocalCcfCaptureCli, existing suites, OFF/ON producers.
  Author's build was in progress (not PASS) at review time; nothing here infers a build or test pass.
- Not claimed: eventual bit neutrality, capture exactness on real data, field truth, global optimum.
