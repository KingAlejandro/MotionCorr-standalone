# MotionCorr project guidance

MotionCorr is a standalone RELION-derived CPU/CUDA motion-correction program.
See `README.md` for builds and usage, and `SOURCE_MANIFEST.txt` for upstream provenance.

## Keep work focused

- Read the relevant issue and latest discussion before changing code.
- Make small changes consistent with the existing C++17, CUDA and Python code.
- Write a short design note for significant algorithm, interface or ownership changes. Routine fixes do not need an ADR.
- Preserve other people's edits, inputs and recorded evidence.
- Agent tools under `agents/` and `skills/` are optional. No fixed agent roles, refinement loop or repeated audits are required.

## Correctness and review

- Preserve numerical results, metadata and failure/publication behavior unless the task explicitly calls for a change. Explain intentional differences.
- Do not relax numerical gates or tolerances to make a result pass.
- When verification is requested, use the relevant existing checks and report the revision, inputs, commands, results and limitations. Planned or unrun checks are not passes.
- Compilation and green CI do not establish native GPU execution, performance or scientific correctness. Keep those claims separate.
- Before recommending a merge, check latest-source review, current-head CI and the validation required for the claim. Review correctness, scope and license compatibility together; no separate reviewer for each category is required.
- Retain upstream notices and use dependencies compatible with the project's GPL-2.0-or-later license.

## Shared resources

- Follow the current task's CPU/GPU allocation and lock rules; check occupancy before running work.
- Leave unrelated processes and services alone, and use writable scratch with sufficient space.
- Record actual resources for benchmarks. Compare timings only under matching conditions.
