# #268 quality-report prototype: independent review R1 (23 Oct 2026)

Reviewed: branch `experiment/268-quality-report-20261023`, head `eeb68f1f7accd7d52e0e745efaade26f6898105f`
(worktree `t3-2566d166`, clean, left unchanged). Base `bbf24607dec537bd13351f061047ea38bd38237b`.
Tested implementation `c347f59f25a2148642130136c6462491c8db36d1` (tree `9a11f683…`). Design/protocol `5f2ca4b8…`.
Reviewer: Sonnet 5.5 sub-agent, read-only review. No SSH, GPU, `nvidia-smi` or remote command. Nothing written outside
`/tmp/motioncorr-q268-review-r1-20261023/`.

## Verdict

**No material finding. The prototype is ready for draft publication at `eeb68f1f`**, provided the parent adds the
limitation wording in "Recommended next action" (docs-only, as a separate summary-only commit). There are seven
non-blocking findings (F1-F7). F1 is the only one that can make the report assert something false, and only for
an input shape that production already mishandles silently.

This verdict covers an experimental, default-OFF observation prototype. It does not cover M4 adoption, schema
approval, any CUDA route, accuracy or timing. Those stay UNRUN or not claimed.

## What I verified

**Source delta (`bbf24607..c347f59f`, 6 source files; `c347f59f..eeb68f1f` touches only `docs/…/issue268_quality_prototype_20261023/`).**

- **Capture hooks.** `alignPatch` (CPU), the shared CUDA core `cudaAlignPatchDeviceWithWorkspace`, and the batched `PatchBatchLog`
  cover every solver call site. The retry path has one solver call (`alignPatch`) and it is instrumented. `SolveCapture` is RAII
  and exception-safe. `active_quality` points into a vector that is never resized during the run.
- **Thread-local capture.** The solvers run their convergence loops on the caller's thread. `noteSolve` sits outside the
  `omp parallel for`. Movies are processed sequentially in `run()`, so the single `active_quality` pointer is safe.
- **OFF-build neutrality.** I stripped every `MC_EXPERIMENTAL_QUALITY_REPORT` conditional with `offtext.py` (keeping `#else` arms)
  and diffed against base (`off_vs_base.diff`). The remaining delta is two includes, one blank line, and
  `bool global_converged` plus a brace pair around the global solver call (`global_converged = alignPatch…`, `(void)global_converged`).
  Braces balance, including in the `#ifdef _CUDA_ENABLED` arm. The `.cu` OFF text differs from base only by one include.
- **Failure semantics.** Sidecars are written after the final writer drain. The aggregate is written before the existing job
  error (`motioncorr_runner.cpp:1131`) or before the rethrow. Every new call that can throw is wrapped, except
  `beginQualityReport`, which runs only with the flag. Write failures only warn on stderr.
- **Evidence binding.**
  - The two evidence namespaces are byte-identical copies of one remote bundle: `diff -rq` of `campaign/` and `receipts/` is
    empty, as are the driver and the sha list. They are one 14-run campaign, not extra runs. The
    top-level `evidence-c347f59f-4gpus/` lacks `fixtures_MANIFEST.json`, `driver.log` and `local_dev/`, which
    only `evidence_c347f59f/` has.
  - All 212 retained campaign files match `remote_campaign_files.sha256`. The other 462 listed files (`.mrcs`, `.mrc`, `.eps`,
    `.pdf`) are hash-only and not retained.
  - The driver sha, the source diff stat, the tree hashes and the binaries receipts match. The argv in `run.json` shows 14 processes
    under `taskset -c 14` with `OMP_NUM_THREADS=1`. 14 campaign runs + 2 parse-only probes = 16, as claimed.
  - Source GPL-2.0-or-later headers are present. The SHA-256 is a textbook FIPS 180-4 implementation. There are no new dependencies.
- **Logs, stdout, stderr.** The campaign checker skips `.log` files. I compared them myself (`cmplogs.sh`, `log_stdout_stderr_compare.out`).
  58 pairs compared across P1/P2/P3/P4, P5/P6, P7/P8, P9/P10 vs P1, P11/P12 and P13/P14. The only differences are wall-time
  lines, the one added stdout line `Experimental quality summary:`, the two intended write-failure warnings, and backtrace
  addresses and paths. Per-movie log preservation holds in the retained data.
- **Independent re-derivation** (`rederive.py`, `extra_fields.py`, no import of the author's checker). 25 sidecars and 7 summaries
  agree on iterations, final RMSD, state, per-patch labels, `converged_patches`, `solver_attempts`, `observations = 5 × converged`,
  `fit_rmsd_x/y` (vs the log line), `max_iter`, route, movie sha (vs the hash list), STAR sha (vs the file), micrograph sha
  (vs the hash list), model state vs the STAR local-model block, strict JSON (no duplicate keys, no NaN or Inf), run-id
  uniqueness, and summary counts and sidecar shas. The P11 mismatches are the expected carried-over
  P4 sidecars (different run id and argv) and the deliberately tampered affine sidecar. No `*.tmp.*` leftovers exist in the retained tree.
  The superseded flat sidecar in P11 is present.

## Controls I ran (all local, none remote)

| Control | Command / artifact | Result |
| --- | --- | --- |
| Author checker selftest | `python3 -B quality_controls.py selftest`, rc 0 | PASS |
| C++ harness for `quality_report.cpp` alone | `ctl/harness.cpp`, `ctl/resume1.cpp`; `clang++ -std=c++17 -O0`, rc 0 | see F2, F3, F6 |
| Checker discrimination probe | `tamper_probe.py` on retained P4 data | see below |
| Mac arm64 CPU build of `eeb68f1f` with ON | `git archive` copy, `cmake -DCMAKE_BUILD_TYPE=Release -DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON`, `--target motioncorr -j2`, rc 0; binary sha256 `ac76a691558d3aa044e080cb3f4368c4911dbb2903de68d8407ead1cdbabca9e` | built |
| Local runs L1-L7 | `ctl2/run_controls.sh`, one thread, tiny fixtures (generator output equals `GENERATION_RECORD.json`) | see below |

An earlier configure attempt failed because system Python has no NumPy (`configure_on_attempt1_nonumpy.log`). I kept it and did not
retry in place. The second configure used `/Users/alex.konstantinov/.local/bin/python3`.

Local runs (Mac, development evidence only, not comparable with the Linux campaign):

- **L2: `--max_iter 0`.** Global state `not_run`, 0 iterations, null RMSD, `solver_returned false`. All 9 patches dropped, model
  `global_only` / `too_few_converged_observations`, exit 0. The consistent behaviour is that `not_run` carries
  `max_iter 0`, and `tolerance_px` comes out 0.5 here (see F6 for the not_assessed case).
- **L5: missing movie plus one good movie.** Exit 1, `failed / movie_error`, `not_assessed`, joint `withheld_movie_failures`. The
  sidecar writes `bytes -1`, global `max_iter 0` and `tolerance_px 0` as placeholders (F6).
- **L1, L4:** report on, 3×3 and 5×5, consistent. **L7:** `--aggregate_only` with the flag is rejected, as designed.
- **L3 and L6:** duplicate movie and shared output root (F1).

The author's content checkers (`check_sidecar_against_log`, `check_model_against_star`, `summary_consistent`)
reject a tampered global iteration count or final RMSD, CPU same-input retries, model state vs the STAR, summary counts and
flipped summary entries. They accept tampering of `solver_returned`, global `route`, `max_iter`, `tolerance_px`,
`solver_attempts`, `device_preparation_declined`, `patches_recorded`, `converged`/`dropped` swapped consistently, per-patch `route`
and `kind`, `observations`, `fit_rmsd`, `largest_delta`, `identity.*`, `movie.bytes` and summary sidecar shas
(`tamper_probe.out`). All of those fields are correct in the retained data (my re-derivation above), but the PASS rows do not
establish them. The README claim (iterations, final RMSD and state agree with the printed values, counts consistent) is accurate as worded.

## Findings (all non-blocking)

**F1. Duplicate movie or shared output root gives wrong entries (low to moderate; reproduced locally).**
`writeQualitySidecars` maps `fn_micrographs[i] → i` and the later duplicate overwrites the earlier (`motioncorr_runner.cpp:1650`).
Entries are then added at `:1681` and `:1692`.
- L3 (same movie listed twice): `quality_summary.json` has 3 entries and `counts.movies = 3`; the joint STAR has 2 rows.
- L6 (`in/affine.mrcs` and `in/affine.mrc`, same output root `in/affine`): production, without the flag, silently overwrites
  the first movie's products and logs (exit 0). With the flag, both entries are `this_run` / `published`, and `in/affine.mrcs` is
  reported `converged`. The one surviving sidecar belongs to `in/affine.mrc` (`iteration_limit`). The report therefore asserts
  `published / converged` for a movie whose products no longer exist.
- Consequence: false reporting, but only for an input that production already corrupts silently. No fix is needed for draft
  publication; document it, or detect a root collision and mark the entry failed and the evidence incomplete.

**F2. Resume trusts the content of a valid-looking sidecar (low).**
`quality_report.cpp:423-456` accepts any sidecar whose schema, movie path and size, `publication=published` and STAR/micrograph shas
match. State fields are copied verbatim. A sidecar with `global_alignment.state = "BOGUS"`, `motion_identifiability = "identifiable"`
or `peak_validity = "valid"` is accepted as `resumed_sidecar` (`ctl/resume_variants.out`). A sidecar with the global block removed is
counted under an empty-string key in `counts`. The "always `not_assessed`" invariant is not enforced on the read side. Only
reachable with hand-edited or foreign sidecars.

**F3. Invalid UTF-8 in a movie path gives invalid JSON (low).**
`quote()` (`quality_report.cpp:107-123`) escapes control characters but passes ill-formed bytes ≥0x80 through. The harness wrote a
sidecar with `0xE9` that a strict UTF-8 JSON reader rejects (`harness.out` C2). Quotes, backslashes, newlines, tabs and control bytes are
escaped correctly (C1). Non-finite numbers are written as `null` (C3).

**F4. A patch interrupted by an exception is labelled `dropped` (low, code inspection, CUDA-weighted).**
The `PatchRecord` is created before the solver runs (`motioncorr_runner.cpp:3778`). If the solver or its preparation throws, the
record has `attempts = []` and `converged = false`. `dropped_patches` is `patches.size() - converged` (`quality_report.cpp:394`),
so the interrupted patch counts as dropped. `patches_recorded < patches_planned` and `publication = failed / movie_error`
expose it. Failure-path sidecars only. Not exercised.

**F5. Restated production guards and constants (low, drift risk).**
`fit_rmsd_threshold` is restated in `const bool rejected = …` (`:4312`) next to the production `if`. `tolerance_px "0.5"`,
`search_range_px "50"` (`:1630`), the batched `solve.tolerance_px = 0.5` (`:3826`), and the JSON literals
`min_observations_exclusive 18`, `distortion_limit_px 3`, `fit_rmsd_limit_px 10` (`quality_report.cpp:412-415`) duplicate runner
constants. Nothing ties them to the production values, so an upstream edit would drift silently. Today they are correct.
`largest_delta_px` is the running maximum up to the first offending frame, because the production loop breaks early (`:4259`).

**F6. Placeholders where null would be honest (nit).**
For `not_assessed` the sidecar emits `movie.bytes: -1`, global `max_iter: 0`, `tolerance_px: 0`. For `bytes_as_string` the
resume path reports `sidecar_stale` rather than `sidecar_invalid`.

**F7. Evidence and protocol gaps (documentation).**
- PROTOCOL.md header: "Frozen before any native run of prototype code". Amendments A1 and A2 record local Mac runs that preceded
  them, so the sentence is not literal. A1 and A2 are prospective for the remote campaign only. The failing
  local development results are not retained; only post-fix `dev1`/`dev2` results are in `local_dev/`.
- The command that produced `static_flag_witness.txt` (and the sha list and `fixtures_MANIFEST.json`) is not in `driver.sh` or any
  retained script. It is a post-driver remote step, so the counting method is unrecorded. The probes' argv, exits and stderr
  are retained. Both probes exited 1 on the earlier "choose MotionCor2 or own implementation" check, so OFF-build flag refusal is
  static only, not measured.
- The checker ignores `.log` and `*.tmp.*` files when comparing products. Both properties hold in the retained data (above),
  but the PASS rows do not test them.
- Only `--target motioncorr` was built. No existing C++ CTest target was built or run on B1, B2 or B3. The CUDA + option OFF
  configuration was never compiled (the text check above shows its delta is the trivial `global_converged` block).
  `QualityReportCheckerSelftest` was run directly, not through ctest.
- Negative controls N1-N5 are checker-level. They cover global state, product bytes, identifiability, publication and patch
  iterations. None targets the resume classification, the hash bindings, model state vs STAR, summary counts or sidecar shas,
  although the checker would catch some of those (probe above). No control mutates the C++ hooks.
- I found no latest-discussion comment on #268 (live comment list empty, and the raw snapshot was also empty). The maintainer
  selection of "Report quality; preserve publication" is therefore documented only in the Notion plan and the task brief.

## Claims confirmed as stated

- E1-E8 and N1-N5 PASS are reproduced from the retained data for everything not hash-only.
- Peak validity and identifiability are always `not_assessed`, including for `flat` (final RMSD 0, `converged`).
- Native process count 16, resources `taskset -c 14`, one numeric thread, 533 MiB scratch.
- CUDA ON is compile-only (B3). Every CUDA route, `operator_error` on the campaign data, distortion-guard and fit-RMSD
  fallback reasons, e10216, dataset and multi-GPU, tomography and timing are UNRUN. Historical 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE
  is untouched (no truth evaluation in this prototype).

## Limitations of this review

Mac arm64 and one host only. The retained `.mrc` products are hash-only, so product identity (E1-E8) was taken from the retained
checker verdicts plus my hash-binding checks, not re-compared byte-for-byte. I did not build or run CUDA. `operator_error` was
not exercised (no cheap CPU trigger found). The local Mac results are development evidence and are not comparable with Linux
(patch convergence counts differ, as the author also notes).

## Recommended next action

1. Publish as a **draft** at `eeb68f1f`, labelled experimental, default-OFF, not M4 adoption, no CUDA execution.
2. Add a docs-only commit, separate from the evidence, that lists F1 (duplicate or colliding output roots), F2 (resume trusts sidecar
   content) and F3 (non-UTF-8 paths) under "Limitations", and corrects the PROTOCOL header sentence (F7).
3. Source follow-ups for the author if the prototype is iterated, not required for the draft: a root-collision check (F1),
   state-vocabulary validation on resume (F2), UTF-8 escaping (F3), `interrupted` instead of `dropped` for a patch that threw (F4).
   Any source change needs fresh exact-SHA evidence and keeps this review's findings open until re-reviewed.
4. Before any adoption discussion: run a CUDA native campaign on the batched, resident, retry and decline routes, and run the CTest suite
   on OFF and ON builds (Section 9 re-entry: publication/report tooling needs the dataset endpoint rows and failure injection).

## Artifacts (all under `/tmp/motioncorr-q268-review-r1-20261023/`)

`rederive.py` / `rederive.out`, `extra_fields.py` / `extra_fields.out`, `tamper_probe.py` / `tamper_probe.out`,
`cmplogs.sh` / `log_stdout_stderr_compare.out`, `offtext.py` / `off_vs_base.diff`, `ctl/harness.cpp` / `ctl/harness.out`,
`ctl/resume1.cpp` / `ctl/resume_variants.out`, `ctl2/run_controls.sh` / `ctl2/run_controls.out`, `ctl2/runs/`,
`configure_on.log`, `build_on.log`, `selftest_local.out`.

Resources: local Mac (arm64, 14 CPUs), load average 4-6 when started; builds `-j2`; every MotionCorr run and harness
used `OMP_NUM_THREADS=1`, `--j 1`; no GPU; no network beyond a read-only `gh api` comment-list refresh. The author worktree and the root
checkout (`c8844894…`) were not modified.
