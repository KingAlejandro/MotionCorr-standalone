# Stage C run 1 result audit (r1)

**Verdict: the report is accurate. The STOP is correct and final under the frozen release. Two LOW wording corrections are needed (F1, F2); neither changes a count, verdict or conclusion.** The B3 STOP comes only from CUDA log timing, as far as the retained data can show. A future *versioned* normalizer that ignores only the two numeric timing values would be a legitimate compatibility repair. It needs a new parent release and must not be applied to run 1.

Scope: one read-only audit by Claude Opus 5.5, without subagents. No SSH, producer, GPU, build, branch or repo change. Scratch is limited to this directory, with ≤2 numeric threads and about 5 MB used.

## Inputs
- Worktree `t3-9c391c37`, HEAD `7bf1a32f41b8f3429b7098246d57fe48fe719740`, clean. `git diff 047aa7a5 HEAD` contains only `docs/`.
- `STAGEC_RUN1_REPORT.md` sha256 `d788cf3e…3fa14` (matches).
- Pins in the tree: driver `b4548145…`, guard `3ec00863…`, pins `c6f6e154…`, ledger `16b545de…` (176 rows: 160 K/N + 16 M). All equal the release fields.
- `parent/PARENT_RELEASE.json` and `runs/release_copy.json` are byte-identical, sha256 `83183e04…461a`. `final_status.release.sha256` is the same value, with `authorized_by: parent` and run id `native-dc-stagec-20261027-r1`.
- `per_run_records.tar.gz` was extracted into a fresh, empty directory by `scripts/safe_extract.py`. It rejects absolute paths, `..`, links and devices, and any path escaping the target. Result: 1225 members, 1125 files, 0 rejected, 0 symlinks.

## Q1: coverage and run integrity (`scripts/q1_recount.py` → `results/q1_recount.json`)
| Claim | Result |
|---|---|
| 95 unique producers of 160 | 95 run dirs, 95 job events, 95 guard logs (all "passed"). Executed ∪ NOT_RUN = ledger K/N set exactly, and the two sets are disjoint |
| all rc 0, SCORED | rc 0 ×95, `row_status` SCORED ×95. Event status equals row status |
| 12 B4 + 80 CPU + 3 CUDA zero | phase 1: 12 CUDA. Phase 2: 80 CPU. Phase 3: J007/J008/J009 (zero CUDA def-unset, exp-unset, exp-none) |
| B4 coverage | all 12: global COVERED at `cuda_single`, local COVERED at `cuda_batched` (eligible frames 5–25 / 45–150), witness VALID |
| 65 NOT_RUN (33 K / 32 N) | 33 K/CUDA + 32 N/CUDA |
| pairs 34/96 | 34 EVALUATED (C-CPU 24, C-BASE 4, C-GOAL 3, C-COMMON 3), 62 NOT_EVALUABLE |
| C-REPRO 16 within 1e-5 | production 8/8, max 5.55e-17. Isotropic 8/8, max 0. All verdicts equal |
| 8 CPU B3 triples identical | all 16 comparisons `identical: true`. Zero-CUDA fails both comparisons, and in both `zero.log` is the only false field |
| per row | every receipt binary hash equals its pin, argv equals expected argv, and every CUDA row has `CUDA_VISIBLE_DEVICES` = the granted UUID |
| manifest | 2712 entries. 1141 entries present in the compact bundle were re-hashed locally, with 0 mismatches. 1571 entries exist only on the host. **This is a partial re-hash, not a full one**: the "2712/2712" figure is host evidence (`post_verify.json`) |
| fixtures 59 unchanged after the run | host evidence only (`post_verify.py` re-hashes the pinned dirs against the pins). Locally 32/59 pinned files exist and match their pin hashes. That supports pin identity only, not the host post-run state |

The 9 `def` rows correctly have no tap or witness file, because that binary does not emit them.

## Q2: science claims, checked independently where local truth exists (`scripts/q2_regrade.py` → `results/q2_regrade.json`)
- **My own re-score.** The field is built from the term order of `ThirdOrderPolynomialModel::getShiftAt` in `src/`, plus the runtime global shift, with u = x/nx−½, v = y/ny−½ and z = frame index. Error is |field−truth|·0.885 Å over ROI rows 12:84 and columns 12:116, with limits .20/.40/.80. It does not import the repo grader. Truth comes from the hash-verified local `*_field.npy` files (hashes equal each row's recorded fixture hash).
- **All 54 K rows with a tap.** Verdicts match the producer in 54/54, with maximum metric difference 7.1e-15 Å. Counts: CPU exp FAIL 25 / PASS 5 / UNIDENT 10, and CUDA exp FAIL 12 / PASS 2, as reported. Tap and STAR verdicts agree on every row.
- **CPU arm-none baseline.** zero PASS 0. integer FAIL .2636, fractional FAIL .5241, affine FAIL .4024, pedestal FAIL 2.1191, noisy FAIL 2.343. flat UNIDENT 2.1044, repeated UNIDENT 16.5339. All as reported. The `def` STAR verdicts (rows with no tap) equal my exp-unset tap verdicts case by case, which is consistent with B3 identity on CPU.
- **N rows** (no N truth available locally, so only the saved values were checked).
  - Counts: production 16 FAIL; isotropic 13 PASS / 3 FAIL. Rounded runtime−STAR = 0 px on all 32 rows.
  - `vel1-N20` iso: arm none 10.4948 / 14.8533 / 14.8599 Å FAIL; arm both 10.4720 FAIL.
  - `vel0-N9` iso: arm none 0.0513 PASS; arm both 3.8885 FAIL.
  - The arm-both values are **bit-identical** to the retained record: runtime 3.8884799367803136 and STAR 3.8884804219647804 in git blob `4fa272f6:…/nc-scores.json`, whose sha256 `dfb0fc42…` equals `retained_cpu_reference.json` `source_sha256`. The arm-none values match `retained_cpu_reference.json` (0.05128, 10.49484). This confirms "matches history" and that the harm still blocks promotion.
- **Conditioned CPU/CUDA, three cases, with a truth-free field difference** (ROI, px, CPU tap vs CUDA tap):
  - C-COMMON (both arms on): affine max 2.6e-5, noisy 4.1e-5, pedestal 2.9e-3. The two fields agree closely, beyond just equal rms.
  - C-BASE pedestal: diff 0, but **both models are all-zero**. Neither backend detects motion, so 2.1191 Å is the full truth magnitude.
  - C-BASE noisy: max 12.6 px apart (the CPU run is NOT_CONVERGED).
  - C-GOAL fields differ by 1.5 to 5.4 px.
  - This is stage-witness and compatibility evidence on three 3×3 cases. Physical accuracy is separate: all are FAIL except zero. **It is not a full-contract pass.**
- **Device attribution.** All 15 CUDA receipts record `gpu_status: UNOBSERVED: no tree pid listed by nvidia-smi compute-apps`, and their procsamples have `gpu: {}` (1–2 samples per row). Attribution rests only on the `CUDA_VISIBLE_DEVICES` binding and the witness counters, not on sampled attribution, as the report states.
- **Performance.** The timing lines are telemetry from a shared GPU with a foreign context. They are not performance evidence and the report makes no timing claim.

## Q3: is the B3 STOP only log timing? (`scripts/q3_normalizer_scratch.py` → `results/q3_normalizer_scratch.json`)
**Yes, as far as the retained data can show.**
- **Logs, checked directly.** The three retained `zero.log` files (hashes equal to manifest lines) were compared with v1 `normalise_console`, extracted verbatim by `ast` from sealed `tools/ccf_dc_native_rows.py` (sha256 `569c33a1…`). The residual differences are exactly:
  - J007/J008: `   Total GPU alignment time:     1.47|1.19 ms` and `  Total Unweighted Reconstruction Time: 0.34|0.25 ms`
  - J008/J009: the Unweighted line only (0.25|0.34)
  - J007/J009: the GPU-alignment line only (1.47|1.19)
  - Output paths and `Full movie wall time` are already normalized.
- **stdout and stderr, checked directly under v1.** Equal for both comparisons.
- **Per-movie `zero.star`.** Raw sha256 `baa09a10…` is identical in all three runs (`inventory.post.json`).
- **Pixels and joint STAR.** These rest on the producer comparator: `pixels: true`, `corrected_micrographs.star: true`. The MRCs are not local, and their raw hashes differ, as expected from the MRC header timestamp. The joint STAR raw hashes differ by path length (747/747/745 bytes).
- **Root cause.** v1's own comment (`ccf_dc_native_rows.py:104`) says the wall-time line is "the only product-log line that differs between two identical runs (measured on repeated identical runs)". That measurement did not include the CUDA profile blocks. This is a gap in the gate's premise, not a producer, harness or science defect. The frozen STOP stays valid and final for run 1.

**Scratch v2 normalizer.** It is v1 plus two fully anchored line patterns: exact label, exact leading spaces, `[0-9]+\.[0-9]{2}`, and ` ms$`.
- v1 reproduces the STOP on all 3 pairs, and v2 makes all 3 equal.
- v2 changes exactly those two lines in each log, and the line count is unchanged.
- On a CPU-shaped log, v2 output equals v1 output.
- 23 controls, all as expected:
  - Timing-only value changes (including wall time): equal under v2.
  - Must FAIL under v2, and did: RMSD value, `converged`, Peak VRAM, Buffer VRAM, local-skip text, frames used, label typo, prefix spacing, unit, `nan`, 3 decimals, trailing text, line deleted, duplicated or moved, Unweighted label changed or deleted, timing plus a semantic change, an inserted DW-timing line, and device id.

**Source facts the continuation needs** (at `96e7e7be`):
- The same `Total GPU alignment time:` label and prefix is also emitted by the batched patch path (`cuda_alignpatch.cu:1084`) and by the non-batched patch/retry path (`:743`). The anchored pattern covers every occurrence while keeping each line's position and count strict.
- Every reached timing value is fixed-point with 2 decimals, because the stream flags are set on the preceding line.
- `Total DW Reconstruction Time` (`cuda_realspace_dw.cu:449`) is not reached by the K267 no-DW argv and should stay strict.

**Disposition (bounded).** A versioned addition (for example a `product-log-normaliser/v2` used by a new `identity_report` version) is a legitimate compatibility repair if all of the following hold:
1. v1 stays frozen, and run 1 stays STOPPED under v1.
2. Only these two numeric values are ignored, only in `{movie}.log`, and not in STAR, stdout or stderr. All label text, spacing, units, line order and counts stay strict.
3. The mutant controls above are part of its tests, including semantic-change-FAIL and timing-only-PASS.
4. Before release, it is applied read-only to the retained host logs (including the 3×3 B4 CUDA logs, which are not in the compact bundle) to show it changes nothing else.
5. The parent writes and reviews a new continuation release for the 65 NOT_RUN rows. The zero-CUDA B3 is re-graded under v2 from the retained J007–J009 data, with no producer retry.

It is a gate amendment and must be described as one. AGENTS forbids relaxing gates to make a result pass; this amendment is acceptable only because the ignored values are telemetry and not program output.

**Residual risk.** Run 1 does not show that the 3×3 CUDA local triples give process-to-process bit-identical STAR and pixels: the zero case is a trivial all-zero 1×1 result. A later B3 STOP on STAR or pixels would be a real result. The normalizer must not be widened in response.

## Findings
- **F1 LOW (wording).** The post-run verification claims "the five binaries … at their pinned hashes". `post_verify.json` covers 3 binaries (`def/exp/iso`) and the guard. The two oracles were hash-checked pre-launch in parent preflight r2 (`oracle_exp 3b93be6a…`, `oracle_iso 99f1f352…`) and are not executed by Stage C. Suggested wording: "the three motioncorr binaries and the guard".
- **F2 LOW (wording).** "Even two `exp` runs (`unset` and `none`) differ in those lines": exp-unset vs exp-none differ only in the Unweighted Reconstruction line, and def vs exp-unset differ in both. The conclusion (run-to-run timing) is unchanged.
- **F3 INFO.** C-BASE pedestal "identical" means two all-zero models. C-COMMON affine and noisy "identical" means equal to 4 decimals (Δrms 5.4e-6 and 1.7e-6 Å). The field differences above make that agreement concrete.
- No count, verdict, hash, coverage or STOP-logic error was found.

## Limitations
- Host-only evidence was not re-checked: post-run fixture re-hash, binaries on disk, locks, the full 2712-file manifest, MRC pixels, joint STAR content and `def` STARs.
- No N truth is available locally, so the N metrics are the producer's.
- Shared GPU with a foreign context and no timing claim. PID sampling missed every CUDA row.
- Not held-out, not tier M, not the full 100, not an adoption decision.
- The report's disclosed home-directory glob (read-only, 1 min) does not affect any result.

## Recommended next step
The parent drafts a short amendment containing: the versioned log-normalizer v2 exactly as in the disposition; its controls; a read-only application to the retained host logs; and a new continuation release for the 65 NOT_RUN rows that starts by re-grading the zero-CUDA B3 from retained data. It goes for review before any producer runs. Correct F1 and F2 with a short superseding note to the run-1 report.

Files: `scripts/` (safe_extract, find_fixtures, q1_recount, q2_regrade, q3_normalizer_scratch), `results/` (JSON outputs and the retained-blob copy), and `SHA256SUMS`.
