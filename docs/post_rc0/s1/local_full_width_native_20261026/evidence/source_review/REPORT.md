# Review: default-off `--experimental_local_full_width_weight` (read-only, independent)

**Verdict: no BLOCK, no MATERIAL source finding.** Source at `634e4b48` implements the authorised brief. Clearance is
conditional and covers source only. It permits the parent to admit a bounded tiny pilot once the real-NumPy local
checks (attempt 2) are accepted and resources are pinned. It is not merge, adoption, CUDA or scientific clearance.

## Pins

| Object | Value |
|---|---|
| Base | `42af54069e9b33a3f6b7b63c4046457c50daa93c` (tree `900ef625…`) |
| Reviewed source | `634e4b486240f4c811c3052d573c6d6ebcc5b298` (tree `9db91248709568990a5e33fd5232b90d2180e78b`) |
| Design commit | `b46379606a2aacdd791b0763fa1784ad0b920ac5` (before code) |
| runner.cpp / .h blobs @634 | `01b2ebd9…` / `e896ca29…` (sha256 `58cdc3c3…` / `88f30d30…`, equal to the author INDEX) |
| test_local_full_width_weight.cpp @634 | blob `01b52609…`, sha256 `2da19afb…` |
| Branch moved during review | `2581b8024ee1bb05f3e700c2b08a63f3d2896d62` = 634 + DESIGN.md only (+19 lines, attempt-2 correction). `git diff --name-only 634..2581` has no non-docs path. Source/test/CMake still `634`. |

Full blob list: `pins.txt`. Diffs: `diff_42af_634.patch`, `diff_634_2581_docs.patch`.

## Source findings (verified against the brief)

- **Predicate and callsite.** `ccfWeightXNorm` returns `pnx` iff `(is_global && iso) || (!is_global && local_full_width)`
  (runner.cpp:5177-5178). The only CPU callsite is alignPatch:4959. alignPatch has exactly two CPU callers: global at
  :3545 (`is_global=true`) and patch at :4002 (`false`). All other patch alignment paths are CUDA, which is refused.
  The global x_norm is the same with the flag on or off, with or without `--experimental_isotropic_weight`, so the
  harmful global arm is preserved.
- **Weight unchanged otherwise.** `ccfWeightAt` (:5181) is untouched. The y normalisation (`nfy = pny`), B, the
  cropped-CCF loop bounds, DC, peak, reference, stopping, fit, rejection, gauge, ROI and publication are not in the diff.
  `x_norm` is an exact int→RFLOAT conversion.
- **Physical frequency.** The x index on the cropped CCF grid is the full-patch Fourier index, so `x/pnx` and
  `ly/pny` are both in cycles/px. This is correct for non-square patches, including per-patch `patch_w`.
- **Default off.** The header initialiser is `false` and `checkOption` defaults to false. With the flag off, the
  expression reduces to the base expression and no log line is written, so default and flag-off runs are
  source-equivalent to the base.
- **Refusal order.** `!do_own` is refused in `read()` (:232). The `MC_DIAG_LOCAL_CCF_DIR` scope term is checked in
  `read()` (:276), and the flag is parsed earlier at :231. The `--gpu` refusal (:456) is inside the
  `do_own && gpu_ids` block, after the device-id syntax checks and before `#if _CUDA_ENABLED`, so it comes before the
  device query, before "built without CUDA" and before the STAR read. All of these run before any movie access. Old
  capture configurations without the flag are unchanged.
- **Witness.** :4961-4962 is outside the OMP region, prints the actual `weight_x_norm`, and prints only when
  `!is_global && flag`. The patch loop (:3690…) is serial. With the flag on, a 3x3 run gets one line per patch
  alignment call. Flag-off and global-only runs get none.
- **Scope.** The diff touches no `.cu`, adds no dependency, and makes no B2, optimiser or default-policy change. The
  GPL-2+ notice in runner.cpp is intact. The new test follows the existing headerless test style.

## Tests and registration (static)

- `LocalFullWidthWeight` can fail for each targeted defect. A callsite passing `false` fails `!same(l_off,l_on)`.
  Using `nfx`, `pnx/2` or a half-width value fails `same(l_on,g_iso)` and the weight asserts. A global leak fails the
  global-invariance asserts. `same(l_on,g_iso)` is a valid equality because, with all other experimental members at
  their defaults, alignPatch's only remaining `is_global` dependences are off (tolerance, half_gain, coupled peak,
  stats, DC arm `none`).
- **No uninitialised-member exposure.** `member_scan.sh` lists every runner member read in alignPatch. Each one either
  has a header initialiser or is set by the test (`use_gpu`, `gpu_id`, `n_threads`, `ccf_downsample`, `max_iter`).
- The CLI additions check: `--gpu 0` refused first, also when combined with iso; the positive configuration reaches
  `no_such_input.star`; non-own is rejected. The capture CLI adds a positive exact-scope control (missing input, no
  capture dir), and the flag counts as unsupported scope.

## LOW

1. **Mutant verdicts are not retained.** In `/tmp/mc-lfw/evidence`, `mut_m1.log` is a NumPy configure failure, and the
   other `mut_*` logs end at "Built target" with no test verdict. They also come from the stub configuration and were
   not rerun in attempt 2. The DESIGN "Mutants caught" line should be read as unretained, attempt-1 only. My static
   analysis above supports the same kill claims, so this is an evidence gap, not a test defect.
2. **DC registration.** `LocalFullWidthWeight` has no `ENVIRONMENT MC_EXPERIMENT_CCF_DC_ARM=none`. A plain ctest in a
   DC build aborts, which fails closed (red). Sibling tests share this pattern. Attempt 2 shows the DC test first
   `***Not Run` because the target was not built, then passing in a separate run (`build-dc-lfw.log`). DESIGN reports
   only the pass.
3. **DESIGN wording.** The test plan was amended in the code commit. The amendments add criteria (witness, capture CLI)
   and relax none. The stale attempt-1 sentence "numpy is absent" remains, though it is superseded by the 2581
   correction section. "Global alignment bit-identical" is a source/analytic-fixture claim. Full-movie global-trajectory
   and byte neutrality are UNRUN. 2581 states this correctly.
4. **Unrefused combination.** The flag can be combined with `--experimental_local_b2`. This is a valid CPU research
   combination but is untested. `MC_DIAG_MODEL_OUT` does not record the flag.

## Local evidence assessment (logs read, not reproduced)

- **Attempt 1 (`/tmp/mc-lfw`) does not qualify.** It used a stub `numpy` on PYTHONPATH (interpreter
  `/opt/homebrew/.../python3.15`), and the stub's own comment falsely says "real numpy is absent on this host".
- **Attempt 2 (`/tmp/mc-lfw2/evidence`)** used `Python3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3`
  (CPython 3.13.7, NumPy 2.4.2). `numpy/__init__.py` sha256 `2e8da3e4…`. Release, both CMakeCaches checked.
  `SHA256SUMS` verifies OK (`SHA256SUMS` itself is sha256 `e70b2348…`). Default build: 6/6 selected tests pass. DC
  build: CcfDcHook, ExperimentalFlagsCli and LocalCcfCaptureCli pass; LocalFullWidthWeight passes on the separate
  rerun.
- **Limitation:** the test commands built from the moving worktree path. Source identity at build time rests on the
  author's statement and on 634..2581 being docs-only.

## Performed / UNRUN

**Performed:** git-object review of 42af..634 (all 7 files) and 634..2581 (docs). Callsite, predicate and guard-order
trace in runner.cpp. Member-initialisation scan (`member_scan.sh`, rc 0, output `member_scan.out`). Read the author
evidence in `/tmp/mc-lfw` and `/tmp/mc-lfw2` and checked attempt-2 SHA256SUMS.

**UNRUN (by brief):** builds, CTest, mutants, numeric reruns, any movie, native or full-field runs, CUDA, SSH or venue
access, field gates (.20/.40/.80 Å), runtime vs actual STAR, N5/9/13/20, harm controls, byte neutrality, scientific
accuracy. No repository edits.

## Scratch artefacts (`/tmp/mc-native-local-full-width-opus-review-20261026-r1`)

`REPORT.md`, `pins.txt`, `diff_42af_634.patch`, `diff_634_2581_docs.patch`, `runner634.cpp`, `runner634.h`,
`test_local_full_width_weight.634.cpp`, `member_scan.sh`, `member_scan.out`, `members.txt`, `alignPatch634.txt`,
`SHA256SUMS`.
