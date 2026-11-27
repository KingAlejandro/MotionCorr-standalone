# cpu1 regrade v2: grader and control readiness (23 October 2026)

**Status: grader and controls ready for independent review. Full regrade UNRUN; 16 CUDA rows UNRUN.**
The original cpu1 subset FAIL (24 rows PASS, pairs 3 PASS / 5 FAIL, N4 PASS) is unchanged. So are the original grader,
the raw `RESULTS.json`/`CPU_SUBSET.json`, the predictions and all earlier evidence. No remote access was used in this task.

- `CONTRACT.md` (frozen first, commit `bab2a17c`). Exact parsed global rows replace the raw-text comparison; every other rule is ported.
- `regrade_v2.py` (sha256 `8bf7b10f…afbaf`). Stdlib only, arguments only, read-only tar or directory input, no imports of the old tools.
- `test_regrade_v2.py` (`a7783cf4…`): 33 controls built from the real retained evidence.
  - The STAR edits are made to real-writer text.
  - MRCs are tiny generated fixtures used only by these controls.
- `remote_precheck.py`, `EVIDENCE_MANIFEST.json` (101 consumed files, from `evidence.tar` `3cc13020…`) and `REMOTE-PLAN.md`. The plan is prospective and needs a fresh review and parent permission.

## Local results (macOS arm64, one process, `OMP_NUM_THREADS=1`; host load 6–8 of 14)

- **Retained evidence** (`evidence/local-star-layer/REGRADE_V2.json`): STAR layer **PASS**, FULL **UNRUN** (no MRC members), exit 2.
  - Row parity with the original grader is exact for all 40 rows.
  - All 8 CPU pairs have exact-equal global rows, including the 5 decision-flip pairs whose raw text differed.
  - N4 kills are exactly A_x, A_y, B_x, B_y, E.
  - Bindings hold: three distinct binaries, each row bound to its arm's receipt, and the 21 injected specs equal to the receipts.
- **Controls:** `evidence/controls-01` has 31/31; `evidence/controls-02` has 33/33 (the same 31 plus the two directory-input controls).
  - Positive: the real evidence; a trailing-zero representation; a full PASS with consistent generated MRCs; extended-header bytes ignored; one MRC missing gives FULL UNRUN.
  - Global-row failures:
    - a value changed by 1e-6;
    - a missing or duplicate frame;
    - a malformed token, NaN, inf;
    - `-0` vs `0`;
    - a wrong label, a missing label, a wrong label index;
    - two global blocks, or none.
  - Image-relation failures: a wrong payload where equal was expected; equal payloads where a flip was expected; a malformed short MRC.
  - Unchanged rules still enforced: an absent overlay line; the mutant taking the candidate's decision (N4); a binary that differs from its receipt; an injected spec that differs; an unbound stdout; a missing CPU row; a CUDA artefact.
  - Invalid input: an unsafe tar member; wrong tar or predictions hashes; an existing output directory; a symlinked file in directory input.
- **Precheck exercised locally** on an extracted copy: PASS; an edited STAR FAIL; a missing MRC FAIL; an existing output refused.
- **Development runs, not retained:** one grader run before the controls (`/tmp/mc264-regrade-v2-dev01`, same result as above). A local directory-path attempt failed before execution because a zsh variable did not word-split (rc 127). It was rerun correctly and then folded into controls-02.

## Semantics to review

- **Equality:** exact `Decimal` value plus sign, so `-1.70013` = `-1.700130` but `-0` ≠ `0`. No tolerance.
- **Fail-closed:** a parse error fails the pair.
- **A deliberate difference from the original:** a missing coefficient index fails the row (`published coefficient index missing`), where the original grader raised. Both fail closed.
- **Image equality** uses the original payload rule (after the 1024-byte header plus the extended header), now with length validation.
- **Limits:** printed precision only, with no full-precision trajectory. Images were never read locally. CPU only.

## 23 October 2026 — additive v2.2 R2B author repair

`AMENDMENT-2.md` froze F1–F4 scope in `614e8184` before implementation. New versioned
`regrade_v2_2.py`, `package_v2_2.py`, `remote_run_v2_2.py`, `test_regrade_v2_2.py` and
`REMOTE-PLAN-v2.2.md` are prepared for fresh independent review. See
[RESPONSE-R2B-v2.2.md](RESPONSE-R2B-v2.2.md) and `evidence-v2.2/author01/` for exact
commands, source/input/runtime hashes, expected refusals and limits.

One local campaign at `dd38b6ad5a67d6aace726d38503b206125752d4e`: **45/45 as intended**,
exit 0. Private-index controls preserve all original fixture files on both local Git
implementations; cumulative/identity and ancestor-writer defects have targeted controls
and separately restored mutants. Measured package: **122,880 bytes**; no full clone.
Retained tar: STAR **PASS**, FULL **UNRUN**, exit 2. Generated MRC controls are synthetic.

**CPU13 remains HELD. Full remote grade and Linux no-write/process/SSH behavior UNRUN.**
R2B's two original failed positives remain FAIL, cause unresolved. Original native
subset FAIL (24 CPU PASS, 3 PASS/5 FAIL pairs, N4 PASS), CUDA16 UNRUN and aggregate
INCOMPLETE are unchanged. Old 65/65 and contaminated 33-mutant records remain exact;
R2B's verdict-changing versus diagnostic-only accounting is retained. No production
source, old contracts/versions/evidence or gates/defaults/policy were changed. Fresh
independent exact-head review and parent scheduling are the next bounded action.
