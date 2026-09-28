# Withdrawn claims

Claims published earlier in this issue that the evidence does not support, and
what replaces them. Raw reports under `raw/` are **not** edited: the record of
what was measured stays as it was written, and the correction lives here and in
the regenerated `support-report.md`.

Each entry names the claim, the field in the preserved raw record that
contradicts it, and the gate that now makes the claim impossible to publish
again. A withdrawal without a gate is a promise; a withdrawal with one is a
contract.

## W1 — Integrated all-24 screen certified native CUDA execution

**Published at 7098a6f** (`support-report.md`, "Integrated candidate: all 24
tutorial movies"):

> - Aggregate equality: pass
>
> | resume | 1 | 24/24 | 0 | pass |

and the closing aggregate, "The declared matrix is complete, every attempted row
passed".

**Contradicted by the same commit's raw record.**
`raw/scarf-gn0005/all24-summary.json` records, for the resume schedule:

```json
"backend_evidence": { "native_cuda_proven": false }
```

alongside `"passed": true` and a top-level `"all24_equal": true`. The witness
was collected and then never read: the pass condition did not consume it, and
the renderer printed a witness cell for `base` only, so the contradiction was
not visible in the published table.

**Withdrawn.** The integrated screen establishes that the three schedules
produce pixel-identical output. It does not establish that native CUDA executed
for every schedule. Those are separate claims and the second one is not
supported by that run.

**Now gated by** `run_all24_schedules.schedule_passed` (the witness is part of
the pass condition whenever `--gpu` is given), `report.all24_witness_holds`
(recomputed from the per-schedule evidence, never from the record's own
`all24_equal`), and `report.render_all24` (a witness cell on every row).
Negative controls `witness_is_consumed` and `report_renders_witness` assert each
of these rejects the historical record.

## W2 — The `batch` schedule's native witness

**Published at 7098a6f**: `| batch | 24 | 24/24 | 0 | pass |` with
`native_cuda_proven: true`.

**Not supported by the record.** `batch` ran 24 separate invocations, but the
pre-fix harness computed the witness from `last["stdout"]` only
(`run_all24_schedules.py:172` at that commit). Twenty-three of the twenty-four
startup markers were never examined and are not in the record. `true` there
means "the last invocation showed a startup marker", not "every invocation did".

**Withdrawn**, and **not recoverable from the preserved record** — the missing
markers are absent, not merely unaggregated. Re-deriving them would be
inventing evidence.

**Now gated by** `report.witness_coverage_gap`, which reports a multi-invocation
schedule lacking `startup_marker_per_invocation` as not covered rather than
crediting it, and by `schedule_witness`, which records the marker for every
invocation. Control: `report_renders_witness`.

## What the historical run does still support

Stated explicitly so the withdrawal is not read as broader than it is.

| Schedule | Invocations | Pixel equality | Native witness in the record |
|---|---:|---|---|
| `base` | 1 | n/a (reference) | complete: 24/24 movies marked, startup marker present |
| `repeat` | 1 | 24/24 exact | complete: 24/24 movies marked, single invocation examined |
| `batch` | 24 | 24/24 exact | **incomplete**: 1 of 24 invocations examined (W2) |
| `resume` | 1 | 24/24 exact | **unproven as recorded** (W1) |

For `resume` the raw record happens to contain the fields the corrected
contract needs, and they are consistent with a pass: `seeded_movies` lists 8
movies, the 8 movies without a stage marker are exactly that set, the 16
executed movies each carry one, and the single invocation recorded
`startup_marker_found: true`. That is a hand re-reading of an old record, not a
harness result, and it is recorded here as an observation only. The corrected
harness has never run on a GPU, so the native integrated screen is **UNRUN**
until a dedicated SCARF execution produces one.

## Status of the replacement evidence

| Claim | Status |
|---|---|
| Gate contracts reject what they are supposed to reject | **PASS** — `negative_controls.py`, CPU, every control asserted against both a good and a bad input |
| Integrated all-24 screen, native CUDA, corrected harness | **UNRUN** — requires a dedicated SCARF allocation |
| Per-row native CUDA matrix, corrected harness | **UNRUN** — same |
| CPU support matrix and gain equality/negative | see `support-report.md` |

Historical CPU/RELION Gate 2 failures remain failures. Nothing here converts one
into a pass, and no withdrawal above upgrades any row.
