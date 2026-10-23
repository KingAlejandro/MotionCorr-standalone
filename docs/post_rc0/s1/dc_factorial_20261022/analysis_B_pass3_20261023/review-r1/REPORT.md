# R1 independent review: #262 Tier B DC factorial, frozen pass-3 snapshot (DRAFT partial-analysis publication)

Reviewer: Sonnet 5.5, fresh task, read-only local. 2026-10-23. No SSH, native, build, GPU, repository edits, nested agents. No decision or production claim.

## Verdict

No finding blocks a DRAFT partial-analysis publication, provided the draft carries the qualifications in F1-F6. The frozen summarizer's arithmetic reproduces exactly. The headline numbers hold. The defects are labelling and inference-scope, not computation. Two parent-side statements are wrong or unsupported (F5, F4).

## What was verified

| Item | Result |
|---|---|
| Snapshot archive SHA-256 | `679d65fd...0767` matches the collected `snapshot.tgz`. 747 regular files, 0 symlinks, no absolute or `..` paths. |
| `SNAPSHOT.json` SHA-256 | `34ed4c76...03a5`, the declared snapshot hash. |
| 736 eval JSONs vs `EVALUATIONS.json` | 0 hash mismatches. The 345 `retained_evaluations` hashes equal the current files. reused 345 + new 391. |
| Record composition | 734 EVALUATED + 2 CONTROL_ONLY. CPU 334, CUDA 402. All native exit 0. |
| Frozen summarizer | Collected `frozen_summarize.py` = `git show b36067fb:.../tools/summarize.py` = `25fc2a25...897`. |
| Evaluator | `git show b36067fb:.../tools/evaluate.py` = `dcc5ddb3...e14d`, equal to `SNAPSHOT.json` `evaluator_sha256`. |
| Imported checker sources | All 111 `source_python_sha256` entries match `git show 3eee0a4b:<path>`. |
| Regenerated summarizer | Local python3 -B, 1 numeric thread, nonblocking lifetime lock. `out/regen/tierB.json` parses equal to the collected `tierB.json` (rows 80, pairs 240, regressions 878). The Tier B section of `tables.md` is byte-identical to the collected `tables-TierB.md` body. |
| Independent recompute | My own code (`scripts/indep.py`, scipy `binomtest`) from the raw per-record JSONs: 240/240 comparisons match on n, W/L/T, p (<1e-12) and median (exact). |
| DC witness audit | Over 734 experiment records: selected stage zeroed == eligible, unselected zeroed == 0, arm string equals arm, at every site. 0 anomalies. |
| Validity | 734/734 `sampling_status` VALID. No OUTSIDE_FIXED_ROI. Global nonconverged 40 and local disabled 40 (all pedestal32; none/local and none/global respectively). |
| Parent numbers | pedestal32 none->both CPU RMS 1.78785->0.29919 px, transfer 0.92623->0.99111; CUDA 1.73835->0.29918, 0.93079->0.99111; field FAIL 9/10 (both) vs 10/10; dose4 0/10 field FAIL, ~0.133 px; outmodel CUDA 10/10 field FAIL ~1.042 px; the single harms cell (outmodel CUDA global RMS, 1 win/9 losses, p=0.021484375, median +2.664e-5 px, no failure transition); category counts 30/185/1/12/12; 878 regressions; CPU first eight conditions complete. All reproduced. |
| Truth independence | `tools/check_realistic_motion.py` (3eee0a4b) builds truth from the analytic `generate_realistic_motion.displacement`. Nothing from either backend's output enters truth. Units: Å = px x pixel_size; PASS needs RMS<=0.20, P95<=0.40, max<=0.80 Å. The image side is a separate hash-verified truth cache. |
| Stability | 96 comparisons complete in both the earlier 345-record `results/tierB.json` and pass 3: 0 changed counts or categories. The 1 harms and 9 of the 30 improves arose in cells that were UNRUN or IN_PROGRESS earlier. |
| Exact sign test | `sign_p` = min(1, 2 x binomial tail), correct. 0 ties in 216 complete comparisons. FREEZE's "median favourable" and the code's `w > l` agree on all 31 flagged cells. |

## Findings

Severity is for a draft publication only.

### F1 (medium) Seeds and conditions are not independent replicates

- Scene is fixed: `test-data/generate_realistic_motion.py:35` (`scene_seed=238267`). The motion field is deterministic (`:45-62`, no RNG). A seed changes only the Poisson draw (`:148,156`).
- The same seed gives identical draws for every dose-1 condition (the file's own comment, `:154`). Because pixels = pedestal + scale x (counts - dose), pedestal0, pedestal32, dose1, contrast025 and contrast4 are affine copies of one noisy dataset per seed.
- Observed (`out/probes-run2.txt`, CPU none-arm RMS, seed 0): pedestal0 0.29948, dose1 0.29963, contrast4 0.29944, contrast025 0.31198. The `both` arm gives 0.29948 for all five conditions to five digits, in all four seeds shown. Dose 0.5/2/4 use the same seed with different Poisson means; they are plausibly correlated but are not affine copies (correlation not tested here).
- Consequence: the 216 complete comparisons are not 216 independent tests. The sign-test p-values describe Poisson-noise variability for one scene and one motion field. They do not support "improves in condition X" as a statement about other scenes or motions. CPU and CUDA also share inputs. Metrics (RMS and max, transfer and top-band) are strongly correlated within a cell.
- Draft wording should say "30 improves / 1 harms nominal labels across non-independent comparisons", not imply 31 findings.

### F2 (medium) Labels have no effect-size floor and no noise calibration

- `frozen_summarize.py:115-116` uses exact float sign. FREEZE defines no magnitude floor, so this is as frozen, but the label strings overstate.
- Of 31 labelled cells, 9 have |median delta| < 1e-2 (px or transfer fraction) and 8 are < 2e-4. Examples: contrast4 CUDA both top-band transfer +1.2e-6 ("improves"); dose1 CPU global transfer +7.5e-6; outmodel CUDA global RMS +2.66e-5 px on a 1.042 px field ("harms"; per-seed max |d| 2.7e-4 px).
- Of the 878 per-seed regressions, 685 are < 1e-3, 461 < 1e-4, 135 < 1e-6; only 27 are >= 1e-2. The count is mostly numerical noise in noise-equivalent conditions (dose, contrast, pedestal0, nonsquare).
- No none-vs-none replicate exists for correctness runs, so CUDA run-to-run variation is uncalibrated here. A 1e-5 px CUDA difference cannot be classed as arm effect or run noise from this snapshot.
- Substantive labelled effects: pedestal32 (19 of 31) and contrast025 (3 CPU cells: global max -0.030 px, both RMS -0.010 px, both max -0.064 px). The rest should be labelled "nominal, sub-threshold".

### F3 (low-medium) Multiplicity: the unadjusted flag is necessary and the quantification is missing

- With n=10 the smallest exact p is 0.001953. Bonferroni over 216 (alpha 2.3e-4) has 0 survivors by construction; over the 54 RMS comparisons also 0.
- BH (assumes independence or positive dependence, which F1 violates): 21 of 31 pass q<0.05, exactly the 21 cells with p=0.001953.
- If all 216 were independent nulls, expected nominal hits are ~4.6 (null P(p<0.05)=0.0215), versus 31 observed, 12 of them outside pedestal32. F1 reduces the effective test count, so the true null expectation is lower still. This does not rescue the non-pedestal32 labels. State it, rather than only "unadjusted".

### F4 (low-medium) Table medians for partial cells are not seed-matched; UNRUN rows print zeros

- CPU outmodel has seeds none 4, global 4, local 3, both 3. The table rows show median RMS none 1.04299 vs both 1.05225, which reads as +0.009 px. On common seeds 0-2: none 1.05263, global 1.05272, local 1.05231, both 1.05225. The difference is cohort, not arm. `frozen_summarize.py:105,176` computes each arm's median over its own seeds.
- `tables-TierB.md` nonsquare CPU rows (n `0/0`) print `0` in every failure column and `0 / 0 (1)` for failure fixed/new/McNemar p. These read as "no failures", not UNRUN. The `n` column and category UNRUN are the only markers.
- The 14 per-seed regressions from the partial CPU outmodel cells are included in the 878.

### F5 (low) "Includes 4 plain controls" is wrong; the plain control is UNRUN for Tier B

- The snapshot has 2 plain records, both CUDA (`B-pedestal32-s00-cuda-plain`, `B-dose1-s00-cuda-plain`, CONTROL_ONLY). The two CPU plain records are in `excluded` (UNRUN or in progress at freeze). Header text: `collect_dc_B_pass3.py:39` and `tables-TierB.md:3`. The correct figure is 734 evaluated + 2 control records, as the parent already suspected.
- The snapshot holds only `eval/B`. No `controls-r2-*` for Tier B exists, so the plain-vs-experiment-`none` byte control on pedestal32-s00 and dose1-s00 is UNRUN for Tier B. Draft should not say it passed.

### F6 (low) Failure-union McNemar hides component transitions

- `frozen_summarize.py:55-61,124-128`: McNemar runs on the union only. 560 of 734 records fail the field-distance gate, which FREEZE calls descriptive for this family, so it dominates the union.
- pedestal32 `both`: global nonconvergence goes 10->0 and local-disabled 10->0 per backend, but the union shows "fixed 1 / new 0" because 9 of 10 seeds still fail the field gate. The components appear only as per-arm counts, with no paired component test. This follows FREEZE ("each component and their union are reported"), but the "failure fixed" column understates the structure. Cite the component counts.

### F7 (low, process) Metric subset and timing

- FREEZE lists P95, global-trajectory RMS, local-component RMS, border and per-band FRC. Paired sign tests are implemented only for RMS, max, in-band transfer and top-band transfer (`frozen_summarize.py:110`). The others have medians only.
- The rules (paired sign test, p<0.05, category definitions) were frozen at `b6cb4d76`/`f3ce649a` before the campaign. The summarizer was committed (`b1a4f13c`, 21:09 BST) after about 48% of Tier B was already evaluated (handoff 20:45Z). The metric subset is therefore post-partial-look, though the test rules are prospective. The 96 stable comparisons (above) show no sign of optional-stopping instability.

### F8 (latent, not triggered here) Non-evaluated records drop out silently

- `frozen_summarize.py:112-113` skips pairs where either record is not EVALUATED, and `:127` labels a cell with fewer than 10 pairs IN_PROGRESS. A NATIVE_FAILURE with a nonzero exit would be labelled IN_PROGRESS instead of a failure (though `failure()` counts `native_exit` into the union, the pair is not in the sign test). A status other than EVALUATED with exit 0 gets `failure()` all false (`:55-61`). This snapshot has 734/734 exit 0 and EVALUATED, so no count is affected. Worth fixing before the full campaign. Do not fix in place here.

### Informational

- Transfer direction (higher = better) holds: in-band transfer max 0.9969. Two top-band values exceed 1 (max 1.0017), so overshoot rewarding is negligible.
- The route witness shows CUDA pedestal32 `none` and `global` run the per-patch single local path (5000 eligible CCFs, unzeroed). `local` and `both` do not (0/0). A CUDA `local` or `both` vs `none` difference there therefore includes a route change, not only DC zeroing. This is consistent with local disabled 10/10 in `none` and `global`, and is not a defect.
- pedestal32 `local` has real per-seed regressions (e.g. CUDA seed 1 RMS 1.6625->1.7603 px, top-band transfer 0.654->0.560). Local-only is mixed, and the regression table already lists them.

## Limits and UNRUN

- Not re-verified: raw movie payloads, the remote RUN/RECEIPT bytes behind `INPUT_VERIFICATION.json` (it lists ids and a scope string only), and the evaluator checkers' own output. I did not re-run `evaluate.py` (needs remote raw outputs; no SSH). Eval JSONs were hash-checked against `EVALUATIONS.json` only.
- Not covered by this snapshot: CUDA/CPU native correctness beyond exit 0 and witness, nonsquare CPU, CPU outmodel (3-4 seeds, IN_PROGRESS), Tier C, cost, plain-default control, accuracy or production adoption.
- Historical evidence untouched. Tier A, iteration 1 and the 21:45 `results/` files were read only. The full-campaign acceptance and M3 decision are the maintainer's.

## Commands and resources

- All runs: `/Users/alex.konstantinov/.local/bin/python3 -B`, one numeric thread (OPENBLAS/OMP = 1), nonblocking lifetime flock `.numeric.lock` via `scripts/lockrun.py`. Host load average at start 5.6 (1 min), top process not mine. Scratch only under this directory, new `inv1/`.
- `tar -xzf snapshot.tgz -C inv1/snap` (after `tar -t` check) exit 0.
- Regenerate: `lockrun.py frozen_summarize.py snap/eval out/regen` exit 0.
- Recompute: `lockrun.py indep.py snap/eval out/indep.json out/regen/tierB.json` exit 0 (first attempt used `python3 -I` and failed on `ModuleNotFoundError: scipy`; a second attempt aborted on a pair-ordering assertion in my own script. Both retained in the history above, not as files. The final script is `scripts/indep.py`).
- Probes: `final_probes.py`. First run exit 1 (my working-directory error; `out/probes.err` and empty `out/probes.txt` retained). Second run exit 0: `out/probes-run2.txt`.
- Parent-owned inputs read only: `/tmp/motioncorr-orchestrator-20261022/dc-B-pass3-collected/*`, the packet under `t3-6c79c479/docs/post_rc0/s1/dc_factorial_20261022/`, `git show` of exact commits `3eee0a4b`, `b36067fb`.

## Recommended next bounded action

Before publishing the draft: (1) add F1 and F2 qualifications and the multiplicity numbers (F3); (2) fix the "4 plain controls" header (F5) and mark UNRUN failure cells as UNRUN (F4); (3) report component failure transitions for pedestal32 (F6). Before any full-campaign summary: tolerate non-EVALUATED records explicitly (F8) and add a none-vs-none correctness replicate if CUDA sub-1e-4 differences are to be interpreted.
