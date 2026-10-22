# W4 affine patch (2,1) oracle — independent review R1

Reviewed: `diag/affine-patch-oracle-20261022` at `0777348396a96ae666435f605e017c9d8071b57a`
(worktree `t3-6c3dca0d`, clean), base `b12a28ba`, protocol commit `c1019f25`. Scope:
`docs/post_rc0/s1/first_divergence_20261022/affine_patch_oracle/` only. Measured layer:
offline double-precision replay of the retained #275 patch (2,1) float32 capture,
plus the oracle's analytic forward model. No native, GPU, science or performance layer.

## Recommendation

No material finding blocks **draft evidence publication**. F1–F4 below are about
claim precision and control power. They do not change any number, label or
historical total. Fix F1 before publishing; F2–F4 are wording changes that can go
in the same summary commit. This is not a recommendation to merge or to accept the
science.

## What I verified (reviewer-run, Mac, one numeric thread)

| Check | Result |
|---|---|
| Re-run `attempt02` script unmodified on the same hash-bound inputs | JSON identical to committed `attempt02.json` except `seconds` |
| Re-run `supplement_post_hoc.py` | byte-identical to committed `supplement01.json` |
| `artifacts.json` hashes, `script_sha256`, supplement→attempt02 binding | all match |
| Protocol prospectiveness | `PROTOCOL.md`/`protocol.json` unchanged `c1019f25`→`0777348`; only the two oracle scratch dirs exist (`00:00:54` attempt01 and `00:01:10` attempt02 mrcs writes), both after the protocol commit at `23:57:23`. A deleted earlier scratch dir cannot be excluded. |
| Scope | the diff `b12a28ba..0777348` touches only the new directory. `src/` and prior evidence are untouched. |
| Independent window-crop control (full complex `fft2`, 64× upsampled grid plus derivative-free refinement; no `rfft`, Hermitian multiplicity or Newton) | all 7 offsets match the author's to ≤ 2.5e-5 px, including `(0,-2)→(-0.582,-0.925)` |
| Independent `R_fm` and centre truth, both backends, frames 1–4 | `R_fm` ≤ 2.4e-5 px; truth ≤ 7e-15 px |
| G-E power (own shift/crop chain), shifting every global state by δ | rel_ac 1e-3 is crossed at δ ≈ 0.003 px (x) and ≈ 0.005 px (y); the other backend's state gives 0.26. G-E pins geometry and state far more tightly than the ±1 px mutants show. |
| Native bookkeeping | `after − before = cand − cand[0]` to ≤ 3e-8 in every captured iteration, and the RMSD replay equals the anchored increment. The supplement02 log comparison agrees. |
| Float vs double CCF maps | ≤ 2.35 float32 ULP at the peak, every frame, both backends. This confirms empirically the sum-of-others reference, the conj order and the weight axis. |
| Fit requirement | `motioncorr_runner.cpp:3823,3852-3855`: n_frames rows per accepted patch, so `n_obs > 18` needs ≥ 4 accepted patches. UNRUN is correct. |
| PR275 chain | `file-index.json` = committed `array_product_index_sha256` at `6ae48678`. The manifest's archive/overlay/CPU/CUDA binary hashes appear in the #275 README/bindings. `MC_CCF_PATCH` exists in the #275 overlay. |
| PR276 boundary | No Python fit is presented as the #276 path. The manifest feeds #276 only if ≥ 4 patches are accepted. |
| Licence | SPDX GPL-2.0-or-later, NumPy only; consistent with AGENTS.md. |

The geometry, sign, render, CCF and units math is correct as far as I checked:
the s* range at frame 4 is 0.736/0.557 px by hand from `A`, the window sizes and the
`(u−g)` inverse map, and global state frame 0 is exactly 0 for both backends, so
anchoring to frame 0 is consistent with the truth reference. The sign of `g` in the
analytic render is witnessed against native data by `cT−d ≤ 0.001 px`. A sign
error there would cost several px.

## Findings

**F1 (claim precision; fix before publication). The frame-0 "anchor effect" is an
exact float32 tie broken by different tie rules, then amplified by the separable
parabola cross-term already found in W4.** Scenario: CPU and CUDA iteration 1, frame
0. In both backends' float32 maps, lattice points `(-1,0)` and `(0,0)` are **exactly
equal**: `attempt02.json` `native_candidate_replay_rows` gives `exact_ties=2`, and my
`C6`/`C1` controls give 0 ULP difference in both float maps. CPU's row-major
strict-max scan keeps `(-1,0)`; CUDA's lane reduction keeps `(0,0)`. Of CPU's
frame-0 term `(-0.087, +0.443)`:
- Moving the separable y-parabola from column x=0 to x=−1 on the *double* map moves y
  from −0.388 to +0.105, which is +0.49 px. This is the W4 cross-term (Hessian
  condition ratio ≈ 3.7).
- float32 rounding at the same winner contributes −0.05 px in y and −0.09 px in x.

CUDA also has exact frame-0 ties at iterations 2 (3-way), 3, 4 and 5 (3-way), and at
frame 1 in iteration 3. The README (`README.md:55-59`) says "the native float map
picks (−1,0) where the double map picks (0,0)" and "CUDA picked (0,0) from an equally
small gap (0.53 ULP)". That frames the effect as a value gap and misses that the
float32 values are tied and that the CPU/CUDA difference is the tie-break rule. The
summary row "float32 map vs double map, same parabola" (`README.md:49`) is also
inaccurate for CPU frame 0, where the parabola is centred on a different lattice
point. Magnitude: this mechanism moves every CPU frame by 0.45 px at iteration 1.
Suggested wording: "exact float32 tie at frame 0 in both backends (0.49/0.53 ULP gap
in double); the CPU first-in-scan and CUDA lane-reduction tie rules pick different
columns, and the separable parabola's cross-term turns the column change into 0.49 px
in y." Also state that the float map is within ~2.3 ULP of the double map while peak
curvature is only 5.6/7.5 ULP. That ratio is why sub-pixel candidates scatter by
0.1–0.6 px even without a winner flip (CUDA iteration 2: 0.19–0.32 px, no flip).

**F2 (control power; wording). The four N-C mutants cannot fail once PC passes and
none of them mutates the estimator.** N-C1..N-C3 change only the expected value
(`affine_patch_oracle.py:445-447`). With PC continuous error ≤ 3.3e-8 px, their
errors are |2μ|, |μx−μy| and 1 px by construction. N-C4 renders the frame with the
opposite sign, which tests the control's render. They show that the comparator reads
the right field; they add no independent power. The author summary's "4 estimator
mutants rejected" overstates this. `README.md:91` puts "separations 11 467 to
72 114×" on the same row as N-C, but those separations exist only for N-E. No new
experiment is needed: G-N (native candidate replay ≤ 2e-8 px) and the ≤ 2.35 ULP
float-vs-double map agreement already constrain the estimator path against native
data, and the README could cite them as the estimator witnesses.

**F3 (claim scope; wording). "Acceptance differs between backends" mixes inputs with
arithmetic.** The two backends enter patch alignment with different global states
(frame 4: CPU `(-2.886, 1.754)`, CUDA `(-3.448, 2.450)`; patch inputs differ, and
the other-state rel_ac is 0.26). No arm runs both backends' float32 arithmetic or tie
rules on the same input. The double replays show that each backend's decision is
sensitive to float32 and tie behaviour on its own input. They do not show that the
CPU/CUDA accept/exclude difference is caused by arithmetic rather than by the
different global trajectories. `README.md:64-73` should say that the backend
difference is not isolated.

**F4 (minor; wording).** G-CS (`affine_patch_oracle.py:408-418`) compares the
oracle's own render with its own `inv`. It cannot detect an error that the render and
the truth share. It is harmless, but the sign witness against native data is `cT−d`
plus G-E, not G-CS. "Input is not the problem" (`README.md:38`) should be scoped to
"at iteration 1, on the fixed-template objective".

## Observations, not findings

- The window-crop bias (0.24–0.61 px on this signal) is the same order as the
  retained affine field-gate FAIL (0.455/0.323 px). The README correctly does not
  claim it explains that FAIL. A future generalised oracle should report this
  comparison per patch, because a non-periodic fixture window is a known way to fake
  estimator bias.
- The capture proposal's stop condition (byte-equal STAR/trajectories against the
  #275 capture-on run) is a good discriminating control for "the selector does not
  enter the numerics".
- Failed attempts are handled correctly. attempt01 crashed in the loader before any
  control was evaluated, is retained, and differs from attempt02 only in the
  CUDA-map loader. That is the protocol's new-attempt rule (`PROTOCOL.md:164-165`),
  not a control failure that would require v2.

## Reviewer control retained as invalid

`independent_controls.py` key `C2b_window_periodic_content_mu_0_-2` = `(12.25, 0)`.
That control is ill-posed: under the B=150 weight only the lowest wave survives, so
the objective is degenerate along a line. It is not used for any conclusion.

## Unresolved

- Patch-level only. The 8 other patches, the #276 fit and the field metric are UNRUN,
  pending the parent-owned 16-process capture.
- The window share is not separated into crop, weight and content periodicity.
- Ringing is attributed but not isolated (≤ 0.001 px on the estimate, so it does not
  affect any conclusion).

## Process note

At 00:42, another task started writing `opus-r1-independent/` inside this review
directory. I did not read, modify or hash it. The parent should check that two
reviewers were not given the same ownership path.

Next bounded action: the author applies the F1–F4 wording in a summary-only commit,
with no recompute needed. The parent then decides on the capture proposal.
