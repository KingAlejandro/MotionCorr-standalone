# Issue #73 — Independent dataset scientific validation

Independent-collection scientific validation of the native CUDA backend.

PR #65 evaluated native CUDA on one collection (EMPIAR-10204 beta-galactosidase, K2, 200 kV) and
stated plainly that its 22 held-out movies share that collection's specimen, session and detector.
This work does not reuse those movies, does not reinterpret that result, and does not treat the
22 held-out tutorial movies as an independent collection.

## Contents

| File | What it is |
| --- | --- |
| [`PROTOCOL.md`](PROTOCOL.md) | **The prospective, frozen protocol.** Target collection, analysis sets, endpoints, margins, harmful controls, execution order, resource requirement, and what the study cannot establish. |
| [`HOST_DATA_SURVEY.md`](HOST_DATA_SURVEY.md) | Read-only survey establishing that no independent raw-movie collection is staged on any project host, and why the two other collections present are unusable. |
| [`results/margins_derivation.json`](results/margins_derivation.json) | Output of `tools/science_issue73/i73_margins.py` — every margin derived from collection physics. |
| [`results/acquisition_manifest.json`](results/acquisition_manifest.json) | Every byte acquired from the public archive, with hashes, against the ≤ 2 GiB cap. |

Tooling lives in [`tools/science_issue73/`](../../tools/science_issue73/), isolated from production
code and from the comparator.

## Status

See `WORKER_STATUS.md` at the repository root for the current run state.

## Scope boundaries

This work owns `docs/issue73/` and `tools/science_issue73/` only. It changes no production kernel,
no comparator threshold, no FFT engine, no precision default, no RNG and no scientific formula. It
reclassifies no historical CPU/RELION Gate 2 failure. Relative image RMSE is preserved as a
non-blocking diagnostic per ADR #66 §4 and is never used as a scientific conclusion.
