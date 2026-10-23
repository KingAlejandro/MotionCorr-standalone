# cpu1 regrade v2: contract (frozen before implementation, 23 October 2026)

**Purpose.** This is a separately versioned grader for the cpu1 native outputs (`3751bd05`). It changes
exactly one comparison. The pair check `same_global_shifts` (raw text up to the next `data_`, `tools/n3.py:69,130`)
is replaced by exact equality of parsed global-shift rows. It is not a repair of the recorded result.
The original subset **FAIL** (24 rows PASS, pairs 3 PASS / 5 FAIL, N4 PASS, 16 CUDA rows UNRUN), the original
grader and the raw `RESULTS.json`/`CPU_SUBSET.json` stay byte-exact. Full N3/N4 stays INCOMPLETE.

**Inputs, explicit and read-only.**
- `--evidence-tar` (sha256 pinned on the command line) or `--scratch-root` (a directory). Only regular
  members are read in memory; nothing is extracted or executed.
- `--predictions` must hash to `6ff11cb5…859e`.
- `--receipts` (`known-observations.json`) must hash to `e178e99f…bf33`.
- `--original-results` must hash to `1e027cef…8052`.
- `--out` is a new directory and is refused if it exists.
- No environment variables or imports of the old tools.

**Unchanged requirements (ported exactly; checked for parity on the retained evidence).**
- Per row: rc 0, no CUDA activity in a CPU arm, at most one guard line.
- Overlay witness: exactly one line (768/512/12, n_obs > 18), and none on Z.
- Decision equals prediction; printed delta within 2e-5 relative.
- STAR local model present iff accept; coefficients `max(|a−b| − 1e-7|b|) ≤ 1e-5`; model presence consistent with the guard line.
- Coverage: 24 CPU rows PASS and 16 CUDA rows UNRUN, with no CUDA artefact.
- N4 PASS, with the mutant differing from the candidate on exactly A_x, A_y, B_x, B_y, E.
- Pairs: images equal iff decisions agree.

**Changed requirement: global rows.**
- **Block.** Exactly one `data_global_shift` block. It ends at the next `data_` line or end of file; comment and blank lines are ignored.
- **Schema.** One `loop_` and exactly the labels `_rlnMicrographFrameNumber #1`, `_rlnMicrographShiftX #2`, `_rlnMicrographShiftY #3`, in that order.
- **Rows.** Exactly 12, frames 1–12 unique and in order. Each row has three tokens: a plain decimal integer frame and finite decimal x, y.
- **Equality.** Base and candidate are equal iff every (frame, x, y) is numerically equal as an exact `Decimal` **and** has the same sign (so `-0` ≠ `0`). No tolerance.
- **Fail closed.** Any parse failure fails the row's pair.

**Additional bindings (fail closed).**
- Each RUN.json binary hash must equal its arm's build receipt (one hash per arm, three distinct).
- Each overlay row's `MC264_N3_COEFFS` must equal the receipt string; no-overlay rows carry none.
- Each RUN.json stdout/stderr path must name its own row.

**Image relation and verdicts.** Image equality is computed from MRC payload bytes (after the 1024-byte header and
the extended header) when every pair-member MRC is present. Otherwise image relation is **UNRUN**, and the result is:
- STAR layer: PASS or FAIL;
- FULL: UNRUN.

The local evidence archive has no MRC members, so locally only the STAR layer can be graded.

**Exit codes.** 0 = FULL PASS; 2 = STAR layer PASS and FULL UNRUN; 1 = any FAIL or invalid input. The report
carries the original 3/5 pair result and the N4 state as historical facts.
