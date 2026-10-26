# W4 first-divergence packet — independent review round 1 (2026-10-22)

Reviewed: diag/known-motion-first-divergence-20261022 @ 7d85898da5f4be168c4b878171cf4426b8968655
(detached in reviewer worktree t3-61f54f7f). No native runs, no GPU, no remote access, no edits to author checkout.

## Verdict
Safe to publish as a DRAFT diagnostic packet after README wording corrections F1–F3 (documentation only; no rerun needed).
Provenance, raw bindings, native receipts, failure retention and scope check out. The core mechanism
(separable-slice parabola cross-term bias inside sum-of-others iteration) is independently reproduced, but
"earliest divergence" and "nonconvergence" are stated more broadly than the evidence supports.

## Verified (independent)
- Scope: `git diff --name-only 805d9de2..7d85898d` touches only docs/post_rc0/s1/first_divergence_20261022/.
- Source: local `git archive --format=tar.gz 805d9de2` sha256 1df40992… = receipt source_archive_sha256 = #275 archive; overlay before-hashes match.
- Overlay diff (receipts logs/overlay.diff) is inert when env unset; neutral global-final equals #275 capture-off global.txt exactly (CPU and CUDA, checked).
- Archive: receipts.tar.gz sha256 26a4ddcb… matches index; 264 members, all 264 hash-match index, 0 unindexed; 72 remote-only.
- Archived remote_build.py/remote_run.py/make_overlay.py/w4_inject.h/campaign-manifest.json identical to daaa2217 and HEAD.
- 12 arms: all exit 0; witness lines present only in injected/fixedref arms; CUDA_VISIBLE_DEVICES=UUID GPU-cd5b9f86…, affinity [14,15], GPU1 lock 19:20:31–19:20:39 UTC; build lock 19:15:35–19:20:00. One NOT MET: fixedref-cuda-fractional 0.4947 px. Iteration-1 frame 4 CUDA (−3.833, 2.833) vs CPU (−3.167, 2.000) confirmed from state files.
- Near-tie inference is quantitatively plausible: in the quadratic peak model the (−3,2) vs (−4,3) lattice values differ by ~0.6 ULP at 4–7 ULP curvature.
- Historical 16 rows match #273 summary.json (805d9de2): 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE; sampling 12 VALID / 4 OUTSIDE_FIXED_ROI.
- Analysis scripts at HEAD equal latest attempt copies; every output JSON's script_sha256 matches. Failed offline attempt01 and launch attempt 1 retained.
- Weight: CPU motioncorr_runner.cpp:4736 and CUDA cuda_alignpatch.cu:126 normalise x by nfx=nx/2+1, y by ny; inherited verbatim from 4499be23 (line 2340). Dose weighting (runner:4911) normalises x by (nfx−1)²·4 = nx², i.e. the code is internally inconsistent.
- GPL: all new .py/.h carry SPDX GPL-2.0-or-later; overlay preserves upstream header.

## Independent mathematics (indep.py: stored .mrcs frames, full complex fft2, full-grid weight, fine-grid band-limited maximum instead of BFGS, own replay)
- 81-offset oracle, production weight: parabola max 0.54400 / RMS 0.31350 px (packet 0.5440/0.3135); fine-grid max error ≤1.4e-4 (grid-limited). Hxy/Hxx 0.677, Hxy/Hyy 0.846; |ρ| 0.756. Isotropic: 0.1686 max (packet 0.169).
- Replays from stored frames (double): sum-of-others 5 it integer 0.493, fractional 0.369; 50 it/tol 1e-9 0.303 / 0.393 (not converged); fixed frame 0: 3e-9 / 0.260; exact max 50 it ~1e-4 / 7e-5. These match the packet's CUDA-capture rows; the CPU-capture double row (0.587, 0.897) differs from a third input by ≤2e-6 perturbation, confirming the ill-conditioning statement — "specified algorithm, double" is a range (0.49–0.59), not one value.
- Linearised iteration (small residuals, fixed winner): separable estimate = M r with M = [[1,a],[b,1]]. Fixed reference Jacobian I−M: eigenvalues ±0.756 (stable). Sum-of-others blends to r_i − mean_{j≠i} r_j, gain N/(N−1): eigenvalues of I − (N/(N−1))M are −1.196 and 0.695 at N=5 (unstable). Exact maximum: −0.25 (stable). Isotropic weight: −0.519, 0.019 (stable). This explains all four replay behaviours.

## Findings
F1 (material, wording/correctness) README.md:139–141 says #264 cannot confound pedestal because it "uses model 0 with a 1×1 patch". #273 summary.json shows pedestal ran 9/9 patches with motion_model_version 1 (ledger.json itself says "all 9 patches also log RMSD 0"). The conclusion may survive (all-zero observations fit to zero under either guard branch) but the stated reason is false for pedestal; #264/#265 are not excluded by model 0 there. Fix the sentence and give the correct reason or mark untested.

F2 (material, claim scope) README.md:13–17 states inputs/weights are correct and the earliest departure is the sub-pixel peak estimate; the weight row (:81) only verifies float-vs-inherited-formula fidelity (≤6e-8), while :119–124 calls the weight a candidate defect. Reviewer replay: isotropic weight with the unchanged production parabola, 5 it/tol 0.5, gives 0.043 px (integer) and 0.049 px (fractional), converged in 3–4 iterations — inside the 0.226 px gate. So either the weight or the estimator alone is sufficient on these fixtures; "earliest" holds only if the inherited weight is taken as the specified objective. Also, the source specifies "Quadratic interpolation by Jasenko", not a continuous maximum, so "departs from what the objective specifies" should read "departs from the maximum of the objective it estimates". State the conditionality; add the isotropic-weight replay as reviewer/offline evidence.

F3 (material, transfer limit) README.md:105–107 ("does not converge even after 50 iterations, so the stopping rule is not the root cause") is specific to N=5. Synthetic phase-ramp frames from the hash-bound target (ndep.py; reviewer probe, not a fixture): production weight + parabola, 50 it, reaches truth for N=9/13/20 (integer motion 0.044/0.002/0.000 px; fractional 0.067/0.001/0.000), while 5 it/tol 0.5 still fails (0.27–0.48 px). Linear eigenvalue is −0.976 at N=9, −0.85 at N=20. For realistic frame counts the stopping rule cuts a slowly converging oscillation and is a co-cause. Add to Limits and to any held-issue text.

F4 (minor) README.md:46 "frozen 0.2–0.45 px band": the frozen manifest says "roughly 0.26–0.34 px"; the 0.2–0.45 band is in analyze_native.py:97 (98855b28, committer time 19:16:41 UTC, before 19:20:31 launch — self-reported time). Outcome unchanged (0.308 inside, 0.495 outside both). State the origin.

F5 (minor) README.md:25–27 states the pedestal float map "is a single value" as fact; it is an offline float32 rounding of a double map plus native zero trajectories; no native map captured (ledger uncertainty already says so). Mark inferred in the Result.

F6 (minor) README.md:150 "biased on anisotropic CCF peaks": the error needs a non-zero cross term (rotated/correlated peak); axis-aligned anisotropy gives none. The 1D parabola is near-exact along its slice (cross-term formula reproduces the output within 0.0026 px); the bias is from slicing through the integer winner.

F7 (minor) README.md:83 "native candidate vs exact-objective parabola" — means exact continuous maximum of the same state; relabel.

F8 (counter-evidence to retain) Isotropic weight is not a safe fix: synthetic N=20 fractional diverges to 11.8 px with the isotropic weight while the production weight gives 0.28 (5 it). Any issue text must present it as diagnostic only.

## Held issue: one or two?
Two distinct held issues, cross-referenced: (1) x-frequency normalisation nx/2+1 vs nx in the alignment B-factor weight (internal inconsistency with dose weighting; affects global and patch alignment; each lever alone fixes the simple fixtures offline; F8 shows the change has its own failure mode). (2) separable 3-point peak estimate on correlated peaks, together with its interaction with sum-of-others gain N/(N−1) and the 5-it/0.5 px stop rule (F3). Both are RELION-inherited, so per current policy file-only with maintainer sign-off before any parity-breaking fix.

## Unresolved
- Native map capture for fixedref-cuda-fractional and pedestal (inferences only).
- Affine/noisy local stages, pedestal patch maps: not localized (acknowledged).
- Neutrality is shown against the #275 capture-off overlay build, which is itself the link to #273 production; chain relies on #275 review.

## Reviewer commands (Mac, Python 3.13 / NumPy 2.4.2 / SciPy 1.17.1, OMP/BLAS/vecLib threads 1, host load ~4)
- `python3 -B -I indep.py /tmp/mc-residual-review.h52lh3/raw indep.json` exit 0
- `python3 -B -I ndep.py /tmp/mc-residual-review.h52lh3/raw indep.py` exit 0 (ndep.log)
- Inputs: integer/fractional .mrcs faaa3f9e…/2dc73085…, fields 3b1f50a5…/7b57149a…, target 287e0a82… — all equal #275 file-index.json (31255dab…, bound by committed 6ae48678 receipt-index).
- Hashes of reviewer files in hashes.txt.
