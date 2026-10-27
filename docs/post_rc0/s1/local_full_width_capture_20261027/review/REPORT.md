# Review: full-width two-patch CCF capture extension (source f473fbc9)

Reviewer: Claude Opus 5.5, read-only, single independent review. Not the author. 2026-10-27.

## Verdict
**CLEAR (source scope only).** No correctness, scope or license defect found in the four-file change. This clears the source for the parent to freeze the two-job diagnostic described in DESIGN.md. It does not grant launch permission, merge, adoption, or any native/byte-compatibility/scientific claim. Native capture, new-binary neutrality, and science remain UNRUN for this source.

## Identity checked
- Worktree HEAD `8d2dfe6e78d793e80ab02001719be3e1a9702e20`, clean. Source `f473fbc9`, tree `f23ed001a7785ad2944f27dcce6bc321b4bcc4f9`.
- `git diff f3f6dfd5 f473fbc9 -- src tests` and `git diff 4ad43a3f f473fbc9 -- src tests` both: 4 files, +139/-19, sha256 `2ef11daa…c180` = `evidence/source.diff` = `source.diff.sha256`.
- `git diff f473fbc9 8d2dfe6e -- src tests CMakeLists.txt cmake`: empty (docs only after source).
- `evidence/SHA256SUMS`: 48 entries, 0 failures.
- Author build tree `/tmp/mc-capext-20261027-r2`: the four touched files equal `git show f473fbc9:<file>`; `motioncorr` `c71fe7f9…6bc8` and `local_ccf_capture` `41319c7a…3005` match `BUILD_IDENTITY.txt`.

## Correctness review (by inspection)
- Mode selection: `motioncorr_runner.cpp:2304-2305` maps the flag to `FullWidthPair`/`Legacy`. The weight denominator comes from the same member via `ccfWeightXNorm` (`:4960`, `:5178-5180`). `configure` receives the same `weight_x_norm` constant used to build the map (`:4970`, `:4974`). Global alignment (`:3546`) passes no capture.
- Coordinates and extents: for 128x96 with a 3x3 grid, `patch_bounds` gives x [0,42),[42,84),[84,126) and y [0,32),[32,64),[64,96). The centres are 20/62/104 and 15/47/79. In FullWidthPair, width 42 and height 32 together with `(xs+xe-1)/2==cx`, `(ys+ye-1)/2==cy` (`local_ccf_capture.h:145`) admit only [84,126)x[0,32) for (104,15) and [42,84)x[64,96) for (62,79). The runner computes centres with the same formula (`:3692`).
- Denominator guard: `local_ccf_capture.h:157` rejects `weight_x_norm != nx(=42)` in FullWidthPair before any configure file is written. `nx==42` is pinned by the preceding require. If the flag-to-mode wiring were inverted from OFF to ON, this check would fail closed.
- Duplicate and coverage: the `seen[]` index (`:237`) is reached only after `selectedCentre`. `finish` requires both entries and `states.size()==2`.
- Metadata: inserts at `size()-2` land before the closing `}`. Legacy strings are untouched. The schema `/2` session literal is separate.
- The following are unchanged: the observer, frame buffers, exclusive writes, budget, null rejected offsets, unclipped fallback, failure before queue/publish, and arithmetic, weight, reference, peak, stopping and fitting.
- Runner guard (`:273-278`): only the `experimental_local_full_width_weight` term was removed. All other refusals remain, and the flag remains refused with `--gpu` (`:456`) and without `--use_own` (`:232`).
- Scope and license: no CMake, CUDA, dependency, CLI or env addition. The files keep their GPL-2.0-or-later SPDX headers, and no third-party code was added.

## Findings
No blocking findings. Observations:
1. **Runner wiring is not covered by tests** (`motioncorr_runner.cpp:2304-2305`, `:4974`). The CLI test stops at the STAR read, before the session is constructed, and the unit tests call the header directly. If the mapping were inverted so that flag ON gave Legacy, the run would silently write schema `/1` with full-width weights, and no test would catch it. The code is correct by inspection. The future capture-ON job should require all of: `session.json` schema `/2`; `fft-config.json` `weight_x_norm` 42; the captured `weights` consistent with x_norm 42 (FUTURE_ANALYSIS_PLAN item 1 already covers this); and the `EXPERIMENTAL local full-width weight: x_norm = 42` log line for the patch alignments.
2. Test naming (`tests/test_local_ccf_capture.cpp`, f1 "wrong extents"): height 31 trips the existing geometry check, not the new centre/extent check. That check is covered by f2 and mutant m7, so there is no coverage gap.
3. The check compares against `ccf_nx`, not `pnx`. Both are 42 under the pinned scope, so there is no effect.

## Evidence audit
- The legacy differential is non-vacuous. The old header in `oldinc/` has sha256 `a0ab50de…` = `4ad43a3f:src/local_ccf_capture.h`. The two dump binaries differ (`ac188502…` vs `8bcbad7a…`), and the string `local_full_width_pair` appears in the new binary only. There are 606 files on each side, and the hash lists are equal.
- Mutants m2-m7 (unit) and m1 (CLI) each fail with their named message, and the unmutated control passes. The amendment accurately records that the duplicate-guard mutant survived in r1 and that the test was strengthened afterwards.

## Reviewer runs (/tmp/mc-fullwidth-ccf-capture-opus-review-20261027-r1)
- `local_ccf_capture` (author binary, OMP 2): rc 0, PASS (`unit.out`).
- `test_local_ccf_capture_cli.py --binary motioncorr` (python -I, DC env unset outside the test): rc 0, PASS (`cli.out`).
- FullWidthPair JSON probe (`probe_fw.sh`, `fwdump/dump_fw.cpp`, standalone, linked to the author's `libmotioncorr_core.a`, OMP 2): build 0, run 0. All 180 JSON files parse. Session `/2` has centres [[104,15],[62,79]]. Patch extents are [84,126,0,32] and [42,84,64,96], both with `weight_x_norm` 42 and inherited value 22. There are 338 files (1.9 MiB, deleted afterwards).
- Failed attempt (kept as `fwdump/attempt1_*`): the first probe build ran under zsh, which did not word-split `$FL`/`$LIBS`, so the build failed with rc 1. It was rerun under bash.
- Nothing was run over SSH, natively, on a GPU, on a movie, on pixels, or for analysis. No branch, source or evidence files were edited.
